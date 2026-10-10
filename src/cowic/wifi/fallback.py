"""Lightweight whitespace-expansion scheduler (base paper, Section 4).

Used by the AP when the MILP is unavailable or returns no optimal schedule.
Instead of solving the optimization, the AP exploits existing whitespace:

1. If an idle gap can hold the whole request, the earliest such gap is used
   and no WiFi FG moves.
2. Otherwise the largest gap is extended as much as possible: overlapping FGs
   are deferred past the window, and the window grows only while no deferred
   FG would miss its deadline or overflow the cycle.

The reserved interval holds the sensing window first, then the
interference-free window. When the request cannot be met in full, the
sensing window keeps priority because it closes the coordination loop.
"""

import time
from collections.abc import Sequence

from cowic.exceptions import ConfigurationError
from cowic.models.frame_group import FrameGroup, SchedulingDecision
from cowic.wifi.baselines import defer_around_window, find_whitespaces
from cowic.wifi.milp_scheduler import ScheduleResult

FALLBACK_STATUS = "fallback_whitespace"
_SEARCH_STEPS = 40  # Bisection steps; resolution is cycle_length / 2**40.


def fallback_whitespace_expansion(
    frame_groups: Sequence[FrameGroup],
    t_start_ms: float,
    t_end_ms: float,
    d_free_ms: float,
    d_sensing_ms: float = 0.0,
) -> ScheduleResult:
    """Reserve ``d_sensing_ms + d_free_ms`` by using or extending a whitespace.

    No FG is ever postponed: when the full request would force a
    postponement, the window is shortened instead.
    """
    if d_free_ms < 0 or d_sensing_ms < 0:
        raise ConfigurationError(
            f"Window durations must be non-negative, got d_free={d_free_ms}, "
            f"d_sensing={d_sensing_ms}"
        )
    began = time.perf_counter()
    gaps = find_whitespaces(frame_groups, t_start_ms, t_end_ms)
    need = d_sensing_ms + d_free_ms

    fitting = [gap for gap in gaps if gap[1] - gap[0] >= need]
    if fitting:
        window_start = fitting[0][0]
        window_end = window_start + need
    else:
        window_start, gap_end = max(
            gaps, key=lambda gap: gap[1] - gap[0], default=(t_start_ms, t_start_ms)
        )
        target = min(window_start + need, t_end_ms)
        window_end = _widest_window(
            frame_groups, window_start, gap_end, target, t_end_ms
        )

    sense_end = min(window_start + d_sensing_ms, window_end)
    return ScheduleResult(
        decisions=defer_around_window(frame_groups, window_start, window_end, t_end_ms),
        t_free_start_ms=sense_end,
        t_free_end_ms=window_end,
        t_sense_start_ms=window_start,
        t_sense_end_ms=sense_end,
        solver_status=FALLBACK_STATUS,
        solve_time_ms=(time.perf_counter() - began) * 1000.0,
    )


def _widest_window(
    frame_groups: Sequence[FrameGroup],
    window_start: float,
    safe_end: float,
    target_end: float,
    t_end_ms: float,
) -> float:
    """Largest feasible window end in ``[safe_end, target_end]``.

    ``safe_end`` (the end of the idle gap) usually never moves an FG, but
    deferral can still cascade: an FG bumped to clear the window's start may
    itself now overlap ``safe_end``, forcing a further, otherwise-avoidable
    postponement. If even ``safe_end`` is infeasible, return ``window_start``
    (an empty window) instead, so the fallback never introduces a
    postponement that would not occur without it.
    """

    def feasible(end: float) -> bool:
        decisions = defer_around_window(frame_groups, window_start, end, t_end_ms)
        return not _any_postponed(decisions)

    if feasible(target_end):
        return target_end
    if not feasible(safe_end):
        return window_start
    low, high = safe_end, target_end
    for _ in range(_SEARCH_STEPS):
        mid = (low + high) / 2.0
        if feasible(mid):
            low = mid
        else:
            high = mid
    return low


def _any_postponed(decisions: list[SchedulingDecision]) -> bool:
    return any(decision.is_postponed for decision in decisions)

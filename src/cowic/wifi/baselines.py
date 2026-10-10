"""AP-side scheduling for the baseline experiments (Table 4).

Each scheme returns the same :class:`ScheduleResult` as the MILP scheduler, so
the simulation engine can drive every experiment through one interface.

* Exp 1 (uncoordinated): WiFi keeps its original timing and the AP grants no
  ZigBee window. ZigBee contends blindly via CSMA/CA.
* Exp 2 (opportunistic): WiFi keeps its original timing. The AP finds the
  largest natural whitespace in the cycle and announces it to ZigBee over
  unidirectional CTC.

Neither baseline reserves a sensing window, so it is reported as an empty
interval at the start of the cycle.
"""

import time
from collections.abc import Sequence

from cowic.exceptions import ConfigurationError
from cowic.models.frame_group import FrameGroup, SchedulingDecision
from cowic.wifi.milp_scheduler import ScheduleResult


def find_whitespaces(
    frame_groups: Sequence[FrameGroup], t_start_ms: float, t_end_ms: float
) -> list[tuple[float, float]]:
    """Return idle ``(start, end)`` intervals in ``[t_start_ms, t_end_ms]``.

    FGs are taken at their original timing and clipped to the cycle, so FGs
    carried over from the previous cycle still block airtime. Overlapping FGs
    are merged. Intervals are returned in time order and have positive length.
    """
    _check_cycle(t_start_ms, t_end_ms)
    busy = sorted(
        (
            max(fg.original_start_ms, t_start_ms),
            min(fg.original_start_ms + fg.duration_ms, t_end_ms),
        )
        for fg in frame_groups
    )
    gaps: list[tuple[float, float]] = []
    cursor = t_start_ms
    for start, end in busy:
        if end <= start:
            continue  # FG lies entirely outside the cycle.
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < t_end_ms:
        gaps.append((cursor, t_end_ms))
    return gaps


def schedule_uncoordinated(
    frame_groups: Sequence[FrameGroup], t_start_ms: float, t_end_ms: float
) -> ScheduleResult:
    """Exp 1: keep WiFi timing unchanged and grant no ZigBee window."""
    _check_cycle(t_start_ms, t_end_ms)
    began = time.perf_counter()
    return _unchanged_result(
        frame_groups,
        free=(t_start_ms, t_start_ms),
        t_start_ms=t_start_ms,
        status="static",
        began=began,
    )


def schedule_opportunistic(
    frame_groups: Sequence[FrameGroup],
    t_start_ms: float,
    t_end_ms: float,
    d_free_ms: float,
) -> ScheduleResult:
    """Exp 2: announce the largest natural whitespace, capped at ``d_free_ms``.

    WiFi is never rescheduled. The window starts at the beginning of the
    largest gap (the earliest one on ties) and lasts ``d_free_ms`` or the gap
    length, whichever is shorter. If the cycle has no idle time, the window
    is empty.
    """
    if d_free_ms < 0:
        raise ConfigurationError(f"d_free_ms must be non-negative, got {d_free_ms}")
    began = time.perf_counter()
    gaps = find_whitespaces(frame_groups, t_start_ms, t_end_ms)
    if gaps:
        gap_start, gap_end = max(gaps, key=lambda gap: gap[1] - gap[0])
        free = (gap_start, min(gap_end, gap_start + d_free_ms))
    else:
        free = (t_start_ms, t_start_ms)
    return _unchanged_result(
        frame_groups,
        free=free,
        t_start_ms=t_start_ms,
        status="gap_search",
        began=began,
    )


def _unchanged_result(
    frame_groups: Sequence[FrameGroup],
    free: tuple[float, float],
    t_start_ms: float,
    status: str,
    began: float,
) -> ScheduleResult:
    decisions = [
        SchedulingDecision(
            fg_id=fg.fg_id,
            scheduled_start_ms=fg.original_start_ms,
            is_postponed=False,
            delay_ms=0.0,
        )
        for fg in frame_groups
    ]
    return ScheduleResult(
        decisions=decisions,
        t_free_start_ms=free[0],
        t_free_end_ms=free[1],
        t_sense_start_ms=t_start_ms,
        t_sense_end_ms=t_start_ms,
        solver_status=status,
        solve_time_ms=(time.perf_counter() - began) * 1000.0,
    )


def _check_cycle(t_start_ms: float, t_end_ms: float) -> None:
    if t_end_ms <= t_start_ms:
        raise ConfigurationError(
            f"Cycle end {t_end_ms} must be after cycle start {t_start_ms}"
        )

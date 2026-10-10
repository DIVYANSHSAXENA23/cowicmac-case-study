"""AP-side scheduling for the baseline experiments (Table 4).

Each scheme returns the same :class:`ScheduleResult` as the MILP scheduler, so
the simulation engine can drive every experiment through one interface.

* Exp 1 (uncoordinated): WiFi keeps its original timing and the AP grants no
  ZigBee window. ZigBee contends blindly via CSMA/CA.
* Exp 2 (opportunistic): WiFi keeps its original timing. The AP finds the
  largest natural whitespace in the cycle and announces it to ZigBee over
  unidirectional CTC.
* Exp 3 (ECC [22]): the AP reserves a fixed window at the start of the cycle
  with a CTS-to-self (NAV) and notifies ZigBee via CTC. The legacy NAV caps
  the reservation at 40 ms. Overlapping WiFi FGs are deferred past it.

No baseline reserves a sensing window, so it is reported as an empty interval
at the start of the cycle.

When driving these schedulers cycle-by-cycle from :func:`traces.playback.
iter_cycles`, pass ``(*cycle.frame_groups, *cycle.active_carryover)``, not
``cycle.frame_groups`` alone: a FG owned by an earlier cycle can still be
transmitting at this cycle's start, and every function below infers "idle"
purely from the FGs it is given.
"""

import math
import time
from collections.abc import Sequence

from cowic.exceptions import ConfigurationError
from cowic.models.frame_group import FrameGroup, SchedulingDecision
from cowic.wifi.milp_scheduler import ScheduleResult

NAV_LIMIT_MS = 40.0  # Longest window legacy NAV can reserve (Section 5.3.1).


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
    return _result(
        _unchanged(frame_groups),
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
    _check_demand(d_free_ms)
    began = time.perf_counter()
    gaps = find_whitespaces(frame_groups, t_start_ms, t_end_ms)
    if gaps:
        gap_start, gap_end = max(gaps, key=lambda gap: gap[1] - gap[0])
        free = (gap_start, min(gap_end, gap_start + d_free_ms))
    else:
        free = (t_start_ms, t_start_ms)
    return _result(
        _unchanged(frame_groups),
        free=free,
        t_start_ms=t_start_ms,
        status="gap_search",
        began=began,
    )


def schedule_ecc(
    frame_groups: Sequence[FrameGroup],
    t_start_ms: float,
    t_end_ms: float,
    d_free_ms: float,
    nav_limit_ms: float = NAV_LIMIT_MS,
) -> ScheduleResult:
    """Exp 3: reserve a fixed NAV window at the cycle start and defer WiFi.

    The window is ``[t_start_ms, t_start_ms + w]`` with
    ``w = min(d_free_ms, nav_limit_ms, cycle length)``; ECC does not adapt
    its position or exceed the NAV limit, whatever ZigBee demands.

    WiFi FGs that collide with the window are deferred as described in
    :func:`defer_around_window`.

    A FG carried over from an earlier cycle (``original_start_ms <
    t_start_ms``, still transmitting at ``t_start_ms``) already started: it
    cannot be deferred or postponed without contradicting its real,
    already-decided schedule. Its original decision is preserved unchanged,
    and the channel is treated as busy until it ends. Since a legacy NAV
    reservation cannot retroactively silence a transmission already in
    progress, the fixed cycle-start NAV is suppressed entirely (reported as
    an empty window) whenever any carryover is active at ``t_start_ms``.
    """
    _check_cycle(t_start_ms, t_end_ms)
    _check_demand(d_free_ms)
    if nav_limit_ms <= 0:
        raise ConfigurationError(f"nav_limit_ms must be positive, got {nav_limit_ms}")
    began = time.perf_counter()

    carryover_ids = {
        fg.fg_id
        for fg in frame_groups
        if fg.original_start_ms < t_start_ms
        and fg.original_start_ms + fg.duration_ms > t_start_ms
    }
    if carryover_ids:
        window_end = t_start_ms
    else:
        window_end = t_start_ms + min(d_free_ms, nav_limit_ms, t_end_ms - t_start_ms)

    carryover_end = max(
        (
            fg.original_start_ms + fg.duration_ms
            for fg in frame_groups
            if fg.fg_id in carryover_ids
        ),
        default=-math.inf,
    )
    by_id: dict[int, SchedulingDecision] = {
        fg.fg_id: _decision(fg, fg.original_start_ms, postponed=False)
        for fg in frame_groups
        if fg.fg_id in carryover_ids
    }
    deferrable = [fg for fg in frame_groups if fg.fg_id not in carryover_ids]
    for decision in defer_around_window(
        deferrable, t_start_ms, window_end, t_end_ms, channel_free_at=carryover_end
    ):
        by_id[decision.fg_id] = decision

    return _result(
        [by_id[fg.fg_id] for fg in frame_groups],
        free=(t_start_ms, window_end),
        t_start_ms=t_start_ms,
        status="ecc_nav",
        began=began,
    )


def defer_around_window(
    frame_groups: Sequence[FrameGroup],
    window_start_ms: float,
    window_end_ms: float,
    t_end_ms: float,
    channel_free_at: float = -math.inf,
) -> list[SchedulingDecision]:
    """Defer FGs that would overlap ``[window_start_ms, window_end_ms]``.

    FGs are served in original order on one channel. An FG keeps its original
    start unless it overlaps the window or an earlier deferred FG, in which
    case it starts as soon as the channel is free again. A deferred FG that
    would then finish after its deadline or after ``t_end_ms`` is postponed to
    the next cycle: it is reported at ``t_end_ms`` with ``is_postponed=True``
    and does not occupy airtime in this cycle. Decisions follow input order.

    ``channel_free_at`` seeds the serialization cursor, for airtime already
    occupied before any FG in ``frame_groups`` (e.g. a carried-over FG the
    caller is tracking separately and has excluded from this list).
    """
    by_id: dict[int, SchedulingDecision] = {}
    for fg in sorted(frame_groups, key=lambda fg: fg.original_start_ms):
        start = max(fg.original_start_ms, channel_free_at)
        overlaps = start < window_end_ms and start + fg.duration_ms > window_start_ms
        if overlaps and window_end_ms > window_start_ms:
            start = window_end_ms  # Kept silent until the window ends.
        end = start + fg.duration_ms
        moved = start > fg.original_start_ms
        if moved and (end > fg.deadline_ms or end > t_end_ms):
            by_id[fg.fg_id] = _decision(fg, t_end_ms, postponed=True)
            continue
        by_id[fg.fg_id] = _decision(fg, start, postponed=False)
        channel_free_at = end
    return [by_id[fg.fg_id] for fg in frame_groups]


def _decision(fg: FrameGroup, start_ms: float, postponed: bool) -> SchedulingDecision:
    return SchedulingDecision(
        fg_id=fg.fg_id,
        scheduled_start_ms=start_ms,
        is_postponed=postponed,
        delay_ms=start_ms - fg.original_start_ms,
    )


def _unchanged(frame_groups: Sequence[FrameGroup]) -> list[SchedulingDecision]:
    return [_decision(fg, fg.original_start_ms, postponed=False) for fg in frame_groups]


def _result(
    decisions: list[SchedulingDecision],
    free: tuple[float, float],
    t_start_ms: float,
    status: str,
    began: float,
) -> ScheduleResult:
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


def _check_demand(d_free_ms: float) -> None:
    if d_free_ms < 0:
        raise ConfigurationError(f"d_free_ms must be non-negative, got {d_free_ms}")

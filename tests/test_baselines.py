"""Tests for the Exp 1, Exp 2 and Exp 3 baseline schedulers."""

import pytest

from cowic.exceptions import ConfigurationError
from cowic.models.frame_group import FrameGroup
from cowic.wifi.baselines import (
    find_whitespaces,
    schedule_ecc,
    schedule_opportunistic,
    schedule_uncoordinated,
)
from traces.playback import frame_groups_from_frame, iter_cycles
from traces.synthetic_generator import build_trace, load_profile


def _fg(fg_id: int, start: float, duration: float, bound: float = 100.0) -> FrameGroup:
    return FrameGroup(
        fg_id=fg_id,
        arrival_time_ms=start,
        duration_ms=duration,
        deadline_ms=start + duration + bound,
        original_start_ms=start,
        qos_sensitive=False,
    )


# Busy: [10, 20], [50, 55], [80, 90] in a [0, 100] cycle.
FGS = [_fg(1, 10.0, 10.0), _fg(2, 50.0, 5.0), _fg(3, 80.0, 10.0)]


def test_find_whitespaces_basic() -> None:
    assert find_whitespaces(FGS, 0.0, 100.0) == [
        (0.0, 10.0),
        (20.0, 50.0),
        (55.0, 80.0),
        (90.0, 100.0),
    ]


def test_find_whitespaces_empty_cycle() -> None:
    assert find_whitespaces([], 0.0, 100.0) == [(0.0, 100.0)]


def test_find_whitespaces_clips_and_merges() -> None:
    fgs = [
        _fg(1, -5.0, 10.0),  # carried over from the previous cycle
        _fg(2, 30.0, 20.0),
        _fg(3, 40.0, 20.0),  # overlaps FG 2
        _fg(4, 95.0, 10.0),  # runs past the cycle end
        _fg(5, 200.0, 5.0),  # outside the cycle
    ]
    assert find_whitespaces(fgs, 0.0, 100.0) == [(5.0, 30.0), (60.0, 95.0)]


def test_find_whitespaces_fully_busy() -> None:
    assert find_whitespaces([_fg(1, 0.0, 100.0)], 0.0, 100.0) == []


def test_uncoordinated_keeps_timing() -> None:
    result = schedule_uncoordinated(FGS, 0.0, 100.0)

    assert [d.fg_id for d in result.decisions] == [1, 2, 3]
    for fg, decision in zip(FGS, result.decisions, strict=True):
        assert decision.scheduled_start_ms == fg.original_start_ms
        assert not decision.is_postponed
        assert decision.delay_ms == 0.0
    assert result.t_free_end_ms - result.t_free_start_ms == 0.0
    assert result.t_sense_end_ms - result.t_sense_start_ms == 0.0
    assert result.solver_status == "static"


def test_opportunistic_picks_largest_gap() -> None:
    result = schedule_opportunistic(FGS, 0.0, 100.0, d_free_ms=62.0)
    assert (result.t_free_start_ms, result.t_free_end_ms) == (20.0, 50.0)
    assert result.solver_status == "gap_search"
    assert all(d.delay_ms == 0.0 for d in result.decisions)


def test_opportunistic_caps_at_demand() -> None:
    result = schedule_opportunistic(FGS, 0.0, 100.0, d_free_ms=12.0)
    assert (result.t_free_start_ms, result.t_free_end_ms) == (20.0, 32.0)


def test_opportunistic_tie_takes_earliest() -> None:
    fgs = [_fg(1, 10.0, 10.0), _fg(2, 30.0, 10.0)]
    result = schedule_opportunistic(fgs, 0.0, 50.0, d_free_ms=62.0)
    assert (result.t_free_start_ms, result.t_free_end_ms) == (0.0, 10.0)


def test_opportunistic_no_idle_time() -> None:
    result = schedule_opportunistic([_fg(1, 0.0, 100.0)], 0.0, 100.0, 62.0)
    assert result.t_free_start_ms == result.t_free_end_ms == 0.0


def test_window_never_overlaps_wifi_on_real_trace() -> None:
    fgs = frame_groups_from_frame(build_trace(load_profile("Traffic_I"), 10.0))
    for cycle in iter_cycles(fgs, cycle_ms=1000.0):
        # Realistic per-cycle driving: the cycle's own FGs plus any FG
        # carried over from an earlier cycle that is still transmitting.
        visible = (*cycle.frame_groups, *cycle.active_carryover)
        result = schedule_opportunistic(visible, cycle.start_ms, cycle.end_ms, 62.0)
        start, end = result.t_free_start_ms, result.t_free_end_ms
        assert cycle.start_ms <= start <= end <= cycle.end_ms
        for fg in visible:
            fg_end = fg.original_start_ms + fg.duration_ms
            assert fg_end <= start or fg.original_start_ms >= end


def test_invalid_inputs() -> None:
    with pytest.raises(ConfigurationError):
        find_whitespaces(FGS, 100.0, 100.0)
    with pytest.raises(ConfigurationError):
        schedule_uncoordinated(FGS, 10.0, 0.0)
    with pytest.raises(ConfigurationError):
        schedule_opportunistic(FGS, 0.0, 100.0, d_free_ms=-1.0)


def _starts(fgs: list[FrameGroup], d_free: float) -> dict[int, float]:
    result = schedule_ecc(fgs, 0.0, 200.0, d_free_ms=d_free)
    return {d.fg_id: d.scheduled_start_ms for d in result.decisions}


@pytest.mark.parametrize(
    ("d_free", "expected_end"), [(31.0, 31.0), (62.0, 40.0), (123.0, 40.0)]
)
def test_ecc_window_capped_by_nav(d_free: float, expected_end: float) -> None:
    result = schedule_ecc([], 0.0, 200.0, d_free_ms=d_free)
    assert (result.t_free_start_ms, result.t_free_end_ms) == (0.0, expected_end)
    assert result.solver_status == "ecc_nav"
    assert result.t_sense_end_ms == result.t_sense_start_ms


def test_ecc_window_capped_by_cycle() -> None:
    result = schedule_ecc([], 0.0, 25.0, d_free_ms=62.0)
    assert result.t_free_end_ms == 25.0


def test_ecc_window_position_is_fixed() -> None:
    # Unlike Exp 2, ECC ignores where natural whitespace is.
    result = schedule_ecc([_fg(1, 0.0, 10.0)], 100.0, 300.0, d_free_ms=31.0)
    assert (result.t_free_start_ms, result.t_free_end_ms) == (100.0, 131.0)


def test_ecc_defers_overlapping_fg_to_window_end() -> None:
    result = schedule_ecc([_fg(1, 10.0, 5.0)], 0.0, 200.0, d_free_ms=31.0)
    (decision,) = result.decisions
    assert decision.scheduled_start_ms == 31.0
    assert decision.delay_ms == 21.0
    assert not decision.is_postponed


def test_ecc_keeps_fg_outside_window() -> None:
    result = schedule_ecc([_fg(1, 50.0, 5.0)], 0.0, 200.0, d_free_ms=31.0)
    (decision,) = result.decisions
    assert decision.scheduled_start_ms == 50.0
    assert decision.delay_ms == 0.0


def test_ecc_fg_straddling_window_end_is_deferred() -> None:
    assert _starts([_fg(1, 25.0, 10.0)], 31.0) == {1: 31.0}


def test_ecc_deferred_fgs_queue_back_to_back() -> None:
    fgs = [_fg(1, 5.0, 10.0), _fg(2, 20.0, 10.0), _fg(3, 45.0, 10.0)]
    # 1 -> [31, 41], 2 -> [41, 51], 3 pushed by 2 -> [51, 61].
    assert _starts(fgs, 31.0) == {1: 31.0, 2: 41.0, 3: 51.0}


def test_ecc_postpones_fg_missing_deadline() -> None:
    fgs = [_fg(1, 10.0, 5.0, bound=10.0), _fg(2, 20.0, 5.0)]
    result = schedule_ecc(fgs, 0.0, 200.0, d_free_ms=31.0)
    first, second = result.decisions
    assert first.is_postponed
    assert first.scheduled_start_ms == 200.0
    assert first.delay_ms == 190.0
    # The postponed FG does not block the channel.
    assert not second.is_postponed
    assert second.scheduled_start_ms == 31.0


def test_ecc_postpones_fg_overflowing_cycle() -> None:
    result = schedule_ecc([_fg(1, 30.0, 20.0)], 0.0, 50.0, d_free_ms=40.0)
    assert result.decisions[0].is_postponed


def test_ecc_keeps_unmoved_fg_crossing_cycle_end() -> None:
    # An FG that was never deferred keeps its original timing.
    result = schedule_ecc([_fg(1, 45.0, 20.0)], 0.0, 50.0, d_free_ms=31.0)
    assert not result.decisions[0].is_postponed
    assert result.decisions[0].scheduled_start_ms == 45.0


def test_ecc_ignores_fg_before_cycle() -> None:
    result = schedule_ecc([_fg(1, -20.0, 5.0)], 0.0, 100.0, d_free_ms=31.0)
    assert result.decisions[0].scheduled_start_ms == -20.0


def test_ecc_preserves_input_order() -> None:
    fgs = [_fg(2, 60.0, 5.0), _fg(1, 10.0, 5.0)]
    result = schedule_ecc(fgs, 0.0, 200.0, d_free_ms=31.0)
    assert [d.fg_id for d in result.decisions] == [2, 1]


@pytest.mark.parametrize("profile", ["Traffic_I", "Traffic_III"])
def test_ecc_invariants_on_real_trace(profile: str) -> None:
    # Unlike Exp 2's gap search, ECC's window position (fixed at the cycle
    # start, Section 5.3.1) never depends on frame_groups, and an FG carried
    # over from an earlier cycle already started in the past: it cannot be
    # deferred to a new time without contradicting its real (already-fixed)
    # schedule. So, unlike schedule_opportunistic, members here is correctly
    # just this cycle's own FGs (cycle.frame_groups) - see #13 review notes
    # on why schedule_ecc is not exposed to the same active_carryover bug
    # that affected schedule_opportunistic.
    fgs = frame_groups_from_frame(build_trace(load_profile(profile), 10.0))
    for cycle in iter_cycles(fgs, cycle_ms=1000.0):
        members = list(cycle.frame_groups)
        result = schedule_ecc(members, cycle.start_ms, cycle.end_ms, 62.0)
        assert result.t_free_end_ms - result.t_free_start_ms == 40.0
        assert len(result.decisions) == len(members)

        by_id = {fg.fg_id: fg for fg in members}
        kept = sorted(
            (d.scheduled_start_ms, d.scheduled_start_ms + by_id[d.fg_id].duration_ms)
            for d in result.decisions
            if not d.is_postponed
        )
        for (_, prev_end), (start, _) in zip(kept, kept[1:], strict=False):
            assert start >= prev_end - 1e-9
        for decision in result.decisions:
            fg = by_id[decision.fg_id]
            assert decision.delay_ms >= 0.0
            if decision.is_postponed:
                continue
            end = decision.scheduled_start_ms + fg.duration_ms
            if decision.delay_ms > 0.0:
                assert end <= fg.deadline_ms
                assert end <= cycle.end_ms
            assert decision.scheduled_start_ms >= result.t_free_end_ms or (
                end <= result.t_free_start_ms
            )


def test_ecc_zero_demand_leaves_wifi_untouched() -> None:
    result = schedule_ecc(FGS, 0.0, 100.0, d_free_ms=0.0)
    assert result.t_free_end_ms == result.t_free_start_ms == 0.0
    assert all(d.delay_ms == 0.0 for d in result.decisions)


def test_ecc_invalid_inputs() -> None:
    with pytest.raises(ConfigurationError):
        schedule_ecc(FGS, 0.0, 100.0, d_free_ms=-1.0)
    with pytest.raises(ConfigurationError):
        schedule_ecc(FGS, 0.0, 100.0, d_free_ms=31.0, nav_limit_ms=0.0)
    with pytest.raises(ConfigurationError):
        schedule_ecc(FGS, 100.0, 0.0, d_free_ms=31.0)

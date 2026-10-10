"""Tests for the Exp 1 and Exp 2 baseline schedulers."""

import pytest

from cowic.exceptions import ConfigurationError
from cowic.models.frame_group import FrameGroup
from cowic.wifi.baselines import (
    find_whitespaces,
    schedule_opportunistic,
    schedule_uncoordinated,
)
from traces.playback import frame_groups_from_frame, iter_cycles
from traces.synthetic_generator import build_trace, load_profile


def _fg(fg_id: int, start: float, duration: float) -> FrameGroup:
    return FrameGroup(
        fg_id=fg_id,
        arrival_time_ms=start,
        duration_ms=duration,
        deadline_ms=start + duration + 100.0,
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
        result = schedule_opportunistic(fgs, cycle.start_ms, cycle.end_ms, 62.0)
        start, end = result.t_free_start_ms, result.t_free_end_ms
        assert cycle.start_ms <= start <= end <= cycle.end_ms
        for fg in fgs:
            fg_end = fg.original_start_ms + fg.duration_ms
            assert fg_end <= start or fg.original_start_ms >= end


def test_invalid_inputs() -> None:
    with pytest.raises(ConfigurationError):
        find_whitespaces(FGS, 100.0, 100.0)
    with pytest.raises(ConfigurationError):
        schedule_uncoordinated(FGS, 10.0, 0.0)
    with pytest.raises(ConfigurationError):
        schedule_opportunistic(FGS, 0.0, 100.0, d_free_ms=-1.0)

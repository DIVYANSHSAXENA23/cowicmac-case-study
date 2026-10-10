"""Tests for the WiFi AP orchestrator state machine."""

import math

import pytest

from cowic.ctc.channel import CTCMessage, MessageType
from cowic.exceptions import ConfigurationError, ProtocolError, TraceError
from cowic.models.frame_group import FrameGroup, SchedulingDecision
from cowic.wifi.ap_orchestrator import (
    WBEACON_KEYS,
    ZBEACON_DEMAND_KEY,
    APOrchestrator,
    APState,
)
from cowic.wifi.fallback import FALLBACK_STATUS
from cowic.wifi.milp_scheduler import ScheduleResult

FGS = [
    FrameGroup(
        fg_id=1,
        arrival_time_ms=10.0,
        duration_ms=10.0,
        deadline_ms=120.0,
        original_start_ms=10.0,
        qos_sensitive=False,
    )
]


class FakeCTC:
    def __init__(self, delivers: bool = True) -> None:
        self.delivers = delivers
        self.sent: list[CTCMessage] = []

    def transmit(self, message: CTCMessage) -> bool:
        self.sent.append(message)
        return self.delivers


class FakeScheduler:
    def __init__(self, status: str = "Optimal", error: Exception | None = None) -> None:
        self.status = status
        self.error = error
        self.calls: list[tuple[float, float, float, float]] = []

    def schedule(
        self,
        frame_groups: list[FrameGroup],
        d_free_ms: float,
        d_sensing_ms: float,
        t_start_ms: float,
        t_end_ms: float,
    ) -> ScheduleResult:
        self.calls.append((d_free_ms, d_sensing_ms, t_start_ms, t_end_ms))
        if self.error is not None:
            raise self.error
        return ScheduleResult(
            decisions=[
                SchedulingDecision(fg.fg_id, fg.original_start_ms + 1.0, False, 1.0)
                for fg in frame_groups
            ],
            t_free_start_ms=50.0,
            t_free_end_ms=50.0 + d_free_ms,
            t_sense_start_ms=40.0,
            t_sense_end_ms=40.0 + d_sensing_ms,
            solver_status=self.status,
            solve_time_ms=1.0,
        )


def _zbeacon(demand: float = 30.0) -> CTCMessage:
    return CTCMessage(MessageType.ZBEACON, "ZC_0", 0.0, {ZBEACON_DEMAND_KEY: demand})


def test_cycle_walks_every_state_in_order() -> None:
    ap = APOrchestrator(FakeCTC(), FakeScheduler())
    ap.process_cycle(FGS, 0.0, 100.0, _zbeacon())
    assert ap.history == [
        APState.MAINTAINING,
        APState.CTC_GATHERING,
        APState.RESCHEDULING,
        APState.CTC_NOTIFYING,
        APState.TRANSMITTING,
        APState.MAINTAINING,
    ]
    assert ap.state is APState.MAINTAINING


def test_consecutive_cycles() -> None:
    ap = APOrchestrator(FakeCTC(), FakeScheduler())
    for cycle in range(3):
        ap.process_cycle(FGS, cycle * 100.0, (cycle + 1) * 100.0, _zbeacon())
    assert len(ap.history) == 1 + 3 * 5


def test_optimal_schedule_is_used() -> None:
    scheduler = FakeScheduler()
    ap = APOrchestrator(FakeCTC(), scheduler, d_sensing_ms=10.0)
    outcome = ap.process_cycle(FGS, 0.0, 100.0, _zbeacon(30.0))

    assert scheduler.calls == [(30.0, 10.0, 0.0, 100.0)]
    assert not outcome.used_fallback
    assert outcome.schedule.solver_status == "Optimal"
    assert outcome.d_free_ms == 30.0


@pytest.mark.parametrize(
    "scheduler",
    [
        FakeScheduler(status="Infeasible"),
        FakeScheduler(error=TraceError("solver failed")),
        None,
    ],
)
def test_falls_back_to_whitespace(scheduler: FakeScheduler | None) -> None:
    ap = APOrchestrator(FakeCTC(), scheduler)
    outcome = ap.process_cycle(FGS, 0.0, 100.0, _zbeacon(30.0))
    assert outcome.used_fallback
    assert outcome.schedule.solver_status == FALLBACK_STATUS
    # Gap [20, 100] holds 30 ms, so the window is [20, 50].
    assert (outcome.schedule.t_free_start_ms, outcome.schedule.t_free_end_ms) == (
        20.0,
        50.0,
    )


def test_unexpected_scheduler_error_propagates() -> None:
    ap = APOrchestrator(FakeCTC(), FakeScheduler(error=RuntimeError("bug")))
    with pytest.raises(RuntimeError):
        ap.process_cycle(FGS, 0.0, 100.0, _zbeacon())


def test_wbeacon_announces_reserved_windows() -> None:
    ctc = FakeCTC(delivers=False)
    ap = APOrchestrator(ctc, FakeScheduler(), d_sensing_ms=10.0, ap_id="AP_7")
    outcome = ap.process_cycle(FGS, 200.0, 300.0, _zbeacon(30.0))

    assert ctc.sent == [outcome.wbeacon]
    assert not outcome.wbeacon_delivered
    wbeacon = outcome.wbeacon
    assert wbeacon.msg_type is MessageType.WBEACON
    assert wbeacon.sender_id == "AP_7"
    assert wbeacon.timestamp_ms == 200.0
    assert tuple(wbeacon.payload) == WBEACON_KEYS
    assert wbeacon.payload == {
        "t_free_start_ms": 50.0,
        "t_free_end_ms": 80.0,
        "t_sense_start_ms": 40.0,
        "t_sense_end_ms": 50.0,
    }


def test_lost_zbeacon_reuses_last_demand() -> None:
    scheduler = FakeScheduler()
    ap = APOrchestrator(FakeCTC(), scheduler)
    ap.process_cycle(FGS, 0.0, 100.0, None)
    ap.process_cycle(FGS, 100.0, 200.0, _zbeacon(40.0))
    ap.process_cycle(FGS, 200.0, 300.0, None)
    assert [call[0] for call in scheduler.calls] == [0.0, 40.0, 40.0]


@pytest.mark.parametrize(
    "message",
    [
        CTCMessage(MessageType.WBEACON, "AP_0", 0.0, {ZBEACON_DEMAND_KEY: 1.0}),
        CTCMessage(MessageType.ZBEACON, "ZC_0", 0.0, {}),
        _zbeacon(-1.0),
        _zbeacon(math.nan),
    ],
)
def test_invalid_zbeacon_rejected(message: CTCMessage) -> None:
    ap = APOrchestrator(FakeCTC(), FakeScheduler())
    with pytest.raises(ProtocolError):
        ap.process_cycle(FGS, 0.0, 100.0, message)


def test_cycle_must_start_in_maintaining() -> None:
    ap = APOrchestrator(FakeCTC(), FakeScheduler())
    ap.state = APState.RESCHEDULING
    with pytest.raises(ProtocolError):
        ap.process_cycle(FGS, 0.0, 100.0, _zbeacon())


def test_illegal_transition_rejected() -> None:
    ap = APOrchestrator(FakeCTC(), FakeScheduler())
    with pytest.raises(ProtocolError):
        ap._advance(APState.TRANSMITTING)


def test_invalid_configuration() -> None:
    with pytest.raises(ConfigurationError):
        APOrchestrator(FakeCTC(), d_sensing_ms=-1.0)
    ap = APOrchestrator(FakeCTC())
    with pytest.raises(ConfigurationError):
        ap.process_cycle(FGS, 100.0, 100.0, None)
    assert ap.state is APState.MAINTAINING

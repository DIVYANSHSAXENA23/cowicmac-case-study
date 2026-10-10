"""WiFi Access Point orchestrator state machine.

Each scheduling cycle walks the AP through a fixed sequence of states:

    MAINTAINING -> CTC_GATHERING -> RESCHEDULING -> CTC_NOTIFYING
    -> TRANSMITTING -> MAINTAINING

1. CTC_GATHERING: read the ZigBee demand from the ZBeacon. If the ZBeacon
   was lost, the last known demand is reused.
2. RESCHEDULING: ask the scheduler (the MILP) for a schedule. If no scheduler
   is configured, it raises a ``CoWiCError``, or it returns a non-optimal
   status, fall back to whitespace expansion. FGs carried over from earlier
   cycles are still on air at the cycle start; they are never moved, and
   rescheduling starts only once they have finished.
3. CTC_NOTIFYING: broadcast the reserved windows in a WBeacon.
4. TRANSMITTING: hand the WiFi decisions to the simulation.

The scheduler and CTC link are injected, so any object with the matching
``schedule`` / ``transmit`` method works (e.g. ``MILPScheduler`` and
``CTCChannel``, or test doubles).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol

from cowic.ctc.channel import CTCMessage, MessageType
from cowic.exceptions import ConfigurationError, CoWiCError, ProtocolError
from cowic.models.frame_group import FrameGroup, SchedulingDecision
from cowic.wifi.fallback import fallback_whitespace_expansion
from cowic.wifi.milp_scheduler import ScheduleResult

# CTC payload keys shared with the ZigBee Coordinator.
ZBEACON_DEMAND_KEY = "d_free_ms"
WBEACON_KEYS = (
    "t_free_start_ms",
    "t_free_end_ms",
    "t_sense_start_ms",
    "t_sense_end_ms",
)

OPTIMAL_STATUSES = frozenset({"Optimal"})  # pulp.LpStatus[pulp.LpStatusOptimal]
CARRYOVER_BUSY_STATUS = "carryover_busy"  # Carryover FGs fill the whole cycle.


class APState(Enum):
    """Operational states of the WiFi Access Point orchestrator."""

    MAINTAINING = auto()
    CTC_GATHERING = auto()
    RESCHEDULING = auto()
    CTC_NOTIFYING = auto()
    TRANSMITTING = auto()


_NEXT_STATE: dict[APState, APState] = {
    APState.MAINTAINING: APState.CTC_GATHERING,
    APState.CTC_GATHERING: APState.RESCHEDULING,
    APState.RESCHEDULING: APState.CTC_NOTIFYING,
    APState.CTC_NOTIFYING: APState.TRANSMITTING,
    APState.TRANSMITTING: APState.MAINTAINING,
}


class Scheduler(Protocol):
    """Anything that can reschedule a cycle, such as ``MILPScheduler``."""

    def schedule(
        self,
        frame_groups: list[FrameGroup],
        d_free_ms: float,
        d_sensing_ms: float,
        t_start_ms: float,
        t_end_ms: float,
    ) -> ScheduleResult: ...


class CTCLink(Protocol):
    """Anything that can deliver a CTC frame, such as ``CTCChannel``."""

    def transmit(self, message: CTCMessage) -> bool: ...


@dataclass(frozen=True)
class CycleOutcome:
    """Everything the AP decided and sent during one scheduling cycle."""

    schedule: ScheduleResult
    d_free_ms: float
    used_fallback: bool
    wbeacon: CTCMessage
    wbeacon_delivered: bool


class APOrchestrator:
    """Manages the WiFi AP transmission queue and cross-technology coordination."""

    def __init__(
        self,
        ctc: CTCLink,
        scheduler: Scheduler | None = None,
        d_sensing_ms: float = 0.0,
        ap_id: str = "AP_0",
        optimal_statuses: frozenset[str] = OPTIMAL_STATUSES,
    ) -> None:
        if not math.isfinite(d_sensing_ms) or d_sensing_ms < 0:
            raise ConfigurationError(
                f"d_sensing_ms must be finite and non-negative, got {d_sensing_ms}"
            )
        self.ctc = ctc
        self.scheduler = scheduler
        self.d_sensing_ms = d_sensing_ms
        self.ap_id = ap_id
        self.optimal_statuses = optimal_statuses
        self.state = APState.MAINTAINING
        self.history: list[APState] = [APState.MAINTAINING]
        self.demand_ms = 0.0

    def process_cycle(
        self,
        frame_groups: Sequence[FrameGroup],
        t_start_ms: float,
        t_end_ms: float,
        zbeacon: CTCMessage | None,
        carryover: Sequence[FrameGroup] = (),
    ) -> CycleOutcome:
        """Execute one scheduling cycle at the AP.

        Args:
            frame_groups: WiFi FGs whose original start lies in this cycle.
            t_start_ms: Cycle start.
            t_end_ms: Cycle end.
            zbeacon: The ZBeacon delivered by CTC this cycle, or ``None`` if it
                was lost or the ZC sent none.
            carryover: FGs owned by earlier cycles that are still transmitting
                at ``t_start_ms`` (``TraceCycle.active_carryover``). They have
                already started, so they are not rescheduled; the scheduler
                and fallback only see airtime after the last one ends, so no
                ZigBee window is announced over them.

        If any step raises, the AP is restored to ``MAINTAINING`` before the
        exception propagates, so one malformed ZBeacon, scheduler bug, or CTC
        transmit failure doesn't permanently strand every later cycle in an
        intermediate state (Section 4.5.2: a coordination failure must not
        compromise baseline network functionality in later cycles).
        """
        if self.state is not APState.MAINTAINING:
            raise ProtocolError(f"Cycle started while AP is in {self.state.name}")
        if t_end_ms <= t_start_ms:
            raise ConfigurationError(
                f"Cycle end {t_end_ms} must be after cycle start {t_start_ms}"
            )
        try:
            return self._run_cycle(
                frame_groups, t_start_ms, t_end_ms, zbeacon, carryover
            )
        except Exception:
            self.state = APState.MAINTAINING
            self.history.append(APState.MAINTAINING)
            raise

    def _run_cycle(
        self,
        frame_groups: Sequence[FrameGroup],
        t_start_ms: float,
        t_end_ms: float,
        zbeacon: CTCMessage | None,
        carryover: Sequence[FrameGroup],
    ) -> CycleOutcome:
        self._advance(APState.CTC_GATHERING)
        if zbeacon is not None:
            self.demand_ms = _read_demand(zbeacon)

        self._advance(APState.RESCHEDULING)
        busy_until = max(
            (fg.original_start_ms + fg.duration_ms for fg in carryover),
            default=t_start_ms,
        )
        if busy_until >= t_end_ms:
            schedule, used_fallback = _carryover_busy(frame_groups, t_end_ms), False
        else:
            schedule, used_fallback = self._reschedule(
                list(frame_groups), max(t_start_ms, busy_until), t_end_ms
            )

        self._advance(APState.CTC_NOTIFYING)
        wbeacon = self._wbeacon(schedule, t_start_ms)
        delivered = self.ctc.transmit(wbeacon)

        self._advance(APState.TRANSMITTING)
        outcome = CycleOutcome(
            schedule=schedule,
            d_free_ms=self.demand_ms,
            used_fallback=used_fallback,
            wbeacon=wbeacon,
            wbeacon_delivered=delivered,
        )
        self._advance(APState.MAINTAINING)
        return outcome

    def _advance(self, target: APState) -> None:
        if _NEXT_STATE[self.state] is not target:
            raise ProtocolError(
                f"Illegal AP transition {self.state.name} -> {target.name}"
            )
        self.state = target
        self.history.append(target)

    def _reschedule(
        self, frame_groups: list[FrameGroup], t_start_ms: float, t_end_ms: float
    ) -> tuple[ScheduleResult, bool]:
        if self.scheduler is not None:
            try:
                result = self.scheduler.schedule(
                    frame_groups,
                    self.demand_ms,
                    self.d_sensing_ms,
                    t_start_ms,
                    t_end_ms,
                )
            except CoWiCError:
                pass
            else:
                if result.solver_status in self.optimal_statuses:
                    return result, False
        fallback = fallback_whitespace_expansion(
            frame_groups, t_start_ms, t_end_ms, self.demand_ms, self.d_sensing_ms
        )
        return fallback, True

    def _wbeacon(self, schedule: ScheduleResult, t_start_ms: float) -> CTCMessage:
        return CTCMessage(
            msg_type=MessageType.WBEACON,
            sender_id=self.ap_id,
            timestamp_ms=t_start_ms,
            payload=dict(
                zip(
                    WBEACON_KEYS,
                    (
                        schedule.t_free_start_ms,
                        schedule.t_free_end_ms,
                        schedule.t_sense_start_ms,
                        schedule.t_sense_end_ms,
                    ),
                    strict=True,
                )
            ),
        )


def _carryover_busy(
    frame_groups: Sequence[FrameGroup], t_end_ms: float
) -> ScheduleResult:
    """No airtime is free this cycle: grant no windows and move nothing."""
    return ScheduleResult(
        decisions=[
            SchedulingDecision(
                fg_id=fg.fg_id,
                scheduled_start_ms=fg.original_start_ms,
                is_postponed=False,
                delay_ms=0.0,
            )
            for fg in frame_groups
        ],
        t_free_start_ms=t_end_ms,
        t_free_end_ms=t_end_ms,
        t_sense_start_ms=t_end_ms,
        t_sense_end_ms=t_end_ms,
        solver_status=CARRYOVER_BUSY_STATUS,
        solve_time_ms=0.0,
    )


def _read_demand(zbeacon: CTCMessage) -> float:
    if zbeacon.msg_type is not MessageType.ZBEACON:
        raise ProtocolError(f"Expected a ZBeacon, got {zbeacon.msg_type.name}")
    if ZBEACON_DEMAND_KEY not in zbeacon.payload:
        raise ProtocolError(f"ZBeacon payload lacks {ZBEACON_DEMAND_KEY!r}")
    demand = zbeacon.payload[ZBEACON_DEMAND_KEY]
    if not math.isfinite(demand) or demand < 0:
        raise ProtocolError(f"ZBeacon demand must be finite and >= 0, got {demand}")
    return demand

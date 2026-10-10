"""Discrete-event simulation engine powered by SimPy.

Wires together, per scheduling cycle, every module built earlier in the
sprint: :class:`~cowic.wifi.ap_orchestrator.APOrchestrator` (WiFi FG
rescheduling + WBeacon), :class:`~cowic.zigbee.coordinator.ZigBeeCoordinator`
(superframe adaptation), :class:`~cowic.ctc.channel.CTCChannel`
(WBeacon/ZBeacon delivery), and :class:`~cowic.sim.channel_medium.ChannelMedium`
(ground-truth collision detection). Time progresses through one SimPy
process advancing from cycle to cycle, so a configured ``duration_s``
reliably bounds ``env.now`` at the end of the run.

Experiment variation (Exp 1-6, Table 4) is driven entirely by
:class:`SimulationConfig`: ``wifi_scheduling`` selects the WiFi scheduler
(a baseline function wrapped in :class:`_BaselineScheduler`, or
:class:`~cowic.wifi.milp_scheduler.MILPScheduler`), ``ctc_direction``
controls whether a ZBeacon is sent each cycle, and ``zigbee_adaptation``
controls whether the ZC runs L-WSA (``"lwsa"``) or ignores the WBeacon and
keeps a fixed, non-adaptive superframe (``"fixed"``).
"""

from dataclasses import dataclass
from pathlib import Path

import simpy
import yaml

from cowic.ctc.channel import CTCChannel, CTCMessage
from cowic.exceptions import ConfigurationError
from cowic.models.frame_group import FrameGroup
from cowic.models.superframe import SuperframeConfig, ZigBeePacket
from cowic.sim.channel_medium import ChannelMedium
from cowic.wifi.ap_orchestrator import APOrchestrator, CycleOutcome, Scheduler
from cowic.wifi.baselines import (
    schedule_ecc,
    schedule_opportunistic,
    schedule_uncoordinated,
)
from cowic.wifi.milp_scheduler import MILPScheduler, ScheduleResult
from cowic.zigbee.coordinator import ZigBeeCoordinator
from cowic.zigbee.lwsa_adapter import LWSAAdapter
from traces.playback import iter_cycles, load_trace
from traces.synthetic_generator import generate_trace

# wifi_scheduling -> the ScheduleResult.solver_status its baseline reports
# on success; APOrchestrator treats any status outside this set as needing
# the whitespace fallback, so each baseline's own status must be accepted.
_BASELINE_STATUS: dict[str, str] = {
    "none": "static",
    "gap_search": "gap_search",
    "ecc_nav": "ecc_nav",
}

TRACE_DATA_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "traces" / "data"
)

# Default pending ZigBee packet queue depth reported each cycle. No issue
# in this sprint covers per-packet ZigBee traffic generation (only WiFi FG
# traces exist); the ZC's demand is modeled as a constant queue depth
# rather than left unmodeled.
DEFAULT_ZIGBEE_PENDING_PACKETS = 5

# A legacy, coexistence-unaware ZigBee superframe (`zigbee_adaptation:
# "fixed"`, Exp 1/2/3/5): a maximal standard CAP+CFP structure, oblivious
# to WiFi activity, re-anchored at each cycle's start.
_FIXED_CAP_SLOTS = 8
_FIXED_CFP_SLOTS = 7
_FIXED_SLOT_DURATION_MS = 0.96 * 4  # BASE_SLOT_DURATION_MS * 2**2


@dataclass(frozen=True)
class SimulationConfig:
    """Global parameters for an experiment run.

    ``wifi_scheduling``, ``ctc_direction``, and ``zigbee_adaptation`` take
    the exact string values used in ``configs/exp*.yaml`` (see
    :meth:`from_yaml`). ``gamma_sensing_weight``/``lambda_delay_weight``/
    ``mu_base_cost`` override :class:`~cowic.wifi.milp_scheduler.MILPScheduler`'s
    defaults when ``wifi_scheduling == "milp_soft_constraint"`` and are
    ignored otherwise.
    """

    scenario_name: str
    duration_s: float
    wifi_trace_path: Path
    d_free_ms: float
    d_sensing_ms: float
    zigbee_period_ms: float
    random_seed: int = 42
    wifi_scheduling: str = "milp_soft_constraint"
    ctc_direction: str = "bidirectional"
    zigbee_adaptation: str = "lwsa"
    ctc_per: float = 0.0
    ctc_delay_ms: float = 0.1
    ctc_max_retries: int = 2
    zigbee_pending_packets: int = DEFAULT_ZIGBEE_PENDING_PACKETS
    gamma_sensing_weight: float | None = None
    lambda_delay_weight: float | None = None
    mu_base_cost: float | None = None

    @classmethod
    def from_yaml(
        cls, config_path: Path, trace_dir: Path = TRACE_DATA_DIR
    ) -> "SimulationConfig":
        """Load an experiment config (``configs/exp*.yaml``), generating
        its WiFi trace on first use and reusing it on later calls with the
        same experiment id, traffic profile, duration, and seed.
        """
        with open(config_path) as handle:
            raw = yaml.safe_load(handle)
        missing = [
            key
            for key in (
                "experiment_id",
                "wifi_scheduling",
                "ctc_direction",
                "zigbee_adaptation",
                "sensing_window_ms",
                "d_free_ms",
                "zigbee_period_ms",
                "duration_s",
                "traffic_profile",
            )
            if key not in raw
        ]
        if missing:
            raise ConfigurationError(f"{config_path}: missing keys {missing}")

        seed = int(raw.get("random_seed", 42))
        duration_s = float(raw["duration_s"])
        profile_stem = Path(raw["traffic_profile"]).stem
        trace_path = trace_dir / f"{raw['experiment_id']}_{profile_stem}_{seed}.parquet"
        if not trace_path.exists():
            generate_trace(raw["traffic_profile"], duration_s, trace_path, seed)

        return cls(
            scenario_name=raw["experiment_id"],
            duration_s=duration_s,
            wifi_trace_path=trace_path,
            d_free_ms=float(raw["d_free_ms"]),
            d_sensing_ms=float(raw["sensing_window_ms"]),
            zigbee_period_ms=float(raw["zigbee_period_ms"]),
            random_seed=seed,
            wifi_scheduling=raw["wifi_scheduling"],
            ctc_direction=raw["ctc_direction"],
            zigbee_adaptation=raw["zigbee_adaptation"],
            gamma_sensing_weight=raw.get("gamma_sensing_weight"),
            lambda_delay_weight=raw.get("lambda_delay_weight"),
            mu_base_cost=raw.get("mu_base_cost"),
        )


class _BaselineScheduler:
    """Adapts an Exp 1-3 baseline function to the AP's ``Scheduler`` protocol.

    The baseline functions take different parameter sets (none take
    ``d_sensing_ms``; ``schedule_uncoordinated`` takes no demand either),
    so this wrapper normalizes them to
    ``schedule(frame_groups, d_free_ms, d_sensing_ms, t_start_ms, t_end_ms)``.
    """

    def __init__(self, wifi_scheduling: str) -> None:
        """Raises ConfigurationError if ``wifi_scheduling`` is not a
        known baseline mode (``"none"``, ``"gap_search"``, ``"ecc_nav"``)."""
        if wifi_scheduling not in _BASELINE_STATUS:
            raise ConfigurationError(
                f"Unknown baseline wifi_scheduling {wifi_scheduling!r}; "
                f"use one of {sorted(_BASELINE_STATUS)}"
            )
        self.wifi_scheduling = wifi_scheduling

    def schedule(
        self,
        frame_groups: list[FrameGroup],
        d_free_ms: float,
        d_sensing_ms: float,
        t_start_ms: float,
        t_end_ms: float,
    ) -> ScheduleResult:
        """Dispatch to the baseline function for ``self.wifi_scheduling``."""
        del d_sensing_ms  # No baseline protects a sensing window.
        if self.wifi_scheduling == "none":
            return schedule_uncoordinated(frame_groups, t_start_ms, t_end_ms)
        if self.wifi_scheduling == "gap_search":
            return schedule_opportunistic(frame_groups, t_start_ms, t_end_ms, d_free_ms)
        return schedule_ecc(frame_groups, t_start_ms, t_end_ms, d_free_ms)


def _build_scheduler(config: SimulationConfig) -> tuple[Scheduler, frozenset[str]]:
    """Return the scheduler for ``config.wifi_scheduling`` and the set of
    its success statuses (statuses that must NOT trigger the AP's
    whitespace fallback)."""
    if config.wifi_scheduling in _BASELINE_STATUS:
        return _BaselineScheduler(config.wifi_scheduling), frozenset(
            {_BASELINE_STATUS[config.wifi_scheduling]}
        )
    if config.wifi_scheduling == "milp_soft_constraint":
        kwargs: dict[str, float] = {}
        if config.gamma_sensing_weight is not None:
            kwargs["gamma"] = config.gamma_sensing_weight
        if config.lambda_delay_weight is not None:
            kwargs["lambda_weight"] = config.lambda_delay_weight
        if config.mu_base_cost is not None:
            kwargs["mu_base"] = config.mu_base_cost
        return MILPScheduler(**kwargs), frozenset({"Optimal"})
    if config.wifi_scheduling == "milp_hard_constraint":
        raise ConfigurationError(
            "wifi_scheduling='milp_hard_constraint' (Exp 5) has no scheduler "
            "implementation yet; tracked separately from Issue #7"
        )
    raise ConfigurationError(f"Unknown wifi_scheduling {config.wifi_scheduling!r}")


def _residual_wifi_fragments(
    schedule: ScheduleResult,
    fg_by_id: dict[int, FrameGroup],
    window_start_ms: float,
    window_end_ms: float,
) -> list[tuple[float, float]]:
    """WiFi FG intervals (clipped to the granted window) the ZC must sense
    and avoid - the AP's schedule is advisory, not a hard guarantee that
    the window is actually clear (Section 4.4)."""
    fragments = []
    for decision in schedule.decisions:
        fg = fg_by_id[decision.fg_id]
        start_ms = max(decision.scheduled_start_ms, window_start_ms)
        end_ms = min(decision.scheduled_start_ms + fg.duration_ms, window_end_ms)
        if end_ms > start_ms:
            fragments.append((start_ms, end_ms))
    return fragments


def _fixed_superframe(cycle_start_ms: float) -> SuperframeConfig:
    """A legacy, WiFi-oblivious superframe for ``zigbee_adaptation: "fixed"``."""
    return SuperframeConfig(
        slot_duration_ms=_FIXED_SLOT_DURATION_MS,
        cap_slots=_FIXED_CAP_SLOTS,
        cfp_slots=_FIXED_CFP_SLOTS,
        beacon_offset_ms=cycle_start_ms,
        beacon_interval_ms=(1 + _FIXED_CAP_SLOTS + _FIXED_CFP_SLOTS)
        * _FIXED_SLOT_DURATION_MS,
    )


def _synthesize_zigbee_packets(
    superframe: SuperframeConfig, cycle_index: int, desired_packet_duration_ms: float
) -> list[ZigBeePacket]:
    """One packet attempt per active CAP/CFP slot of ``superframe``.

    Whether a packet actually survives is decided downstream by
    :class:`~cowic.sim.channel_medium.ChannelMedium`'s real overlap check
    against registered WiFi transmissions - this only lays out *when* each
    node attempts to transmit.
    """
    if superframe.cap_slots == 0 and superframe.cfp_slots == 0:
        return []
    packets: list[ZigBeePacket] = []
    cap_start_ms = superframe.beacon_offset_ms + superframe.slot_duration_ms
    for i in range(superframe.cap_slots):
        slot_start_ms = cap_start_ms + i * superframe.slot_duration_ms
        duration_ms = min(superframe.slot_duration_ms, desired_packet_duration_ms)
        packets.append(
            ZigBeePacket(
                packet_id=cycle_index * 1000 + len(packets),
                node_id=0,
                start_time_ms=slot_start_ms,
                duration_ms=duration_ms,
                payload_bytes=32,
                is_cfp=False,
            )
        )
    cfp_start_ms = cap_start_ms + superframe.cap_slots * superframe.slot_duration_ms
    for j in range(superframe.cfp_slots):
        slot_start_ms = cfp_start_ms + j * superframe.slot_duration_ms
        packets.append(
            ZigBeePacket(
                packet_id=cycle_index * 1000 + len(packets),
                node_id=0,
                start_time_ms=slot_start_ms,
                duration_ms=superframe.slot_duration_ms,
                payload_bytes=32,
                is_cfp=True,
            )
        )
    return packets


@dataclass
class _RunStats:
    """Mutable accumulator for the per-run summary returned by ``run()``."""

    cycles_run: int = 0
    total_frame_groups: int = 0
    postponed_frame_groups: int = 0
    fallback_cycles: int = 0
    wbeacon_delivered: int = 0
    wbeacon_lost: int = 0
    csma_ca_fallback_cycles: int = 0
    zigbee_packets_attempted: int = 0
    max_fg_delay_ms: float = 0.0

    def record_cycle(self, outcome: CycleOutcome) -> None:
        """Fold one completed AP cycle's outcome into the running totals."""
        self.cycles_run += 1
        if outcome.used_fallback:
            self.fallback_cycles += 1
        if outcome.wbeacon_delivered:
            self.wbeacon_delivered += 1
        else:
            self.wbeacon_lost += 1
        for decision in outcome.schedule.decisions:
            self.total_frame_groups += 1
            if decision.is_postponed:
                self.postponed_frame_groups += 1
            self.max_fg_delay_ms = max(self.max_fg_delay_ms, decision.delay_ms)

    def finalize(self, medium: ChannelMedium, horizon_ms: float) -> dict[str, float]:
        """Combine the accumulated totals with ``medium``'s final
        collision outcomes into the summary dict returned by ``run()``."""
        wifi_success = sum(
            1 for r in medium.successful_transmissions() if r.protocol == "wifi"
        )
        wifi_failed = sum(
            1 for r in medium.failed_transmissions() if r.protocol == "wifi"
        )
        zigbee_success = sum(
            1 for r in medium.successful_transmissions() if r.protocol == "zigbee"
        )
        zigbee_failed = sum(
            1 for r in medium.failed_transmissions() if r.protocol == "zigbee"
        )
        total_wifi = wifi_success + wifi_failed
        total_zigbee = zigbee_success + zigbee_failed
        return {
            "simulated_duration_ms": horizon_ms,
            "cycles_run": float(self.cycles_run),
            "total_frame_groups": float(self.total_frame_groups),
            "postponed_frame_groups": float(self.postponed_frame_groups),
            "fallback_cycles": float(self.fallback_cycles),
            "wbeacon_delivered": float(self.wbeacon_delivered),
            "wbeacon_lost": float(self.wbeacon_lost),
            "csma_ca_fallback_cycles": float(self.csma_ca_fallback_cycles),
            "max_fg_delay_ms": self.max_fg_delay_ms,
            "zigbee_packets_attempted": float(self.zigbee_packets_attempted),
            "wifi_transmissions": float(total_wifi),
            "wifi_success_count": float(wifi_success),
            "wifi_drop_rate": (wifi_failed / total_wifi) if total_wifi else 0.0,
            "zigbee_transmissions": float(total_zigbee),
            "zigbee_success_count": float(zigbee_success),
            "zigbee_success_rate": (
                (zigbee_success / total_zigbee) if total_zigbee else 0.0
            ),
        }


class SimulationEngine:
    """Coordinates the SimPy discrete-event simulation environment."""

    def __init__(self, config: SimulationConfig) -> None:
        """Store ``config``; ``run()`` does all the actual work."""
        self.config = config
        self.last_medium: ChannelMedium | None = None

    def run(self) -> dict[str, float]:
        """Execute the discrete-event simulation scenario.

        Returns:
            A summary dict (see :meth:`_RunStats.finalize`). Raw
            per-transmission event records remain available afterwards
            via ``self.last_medium.transmissions`` (a documented run
            artifact: :class:`~cowic.sim.channel_medium.ChannelMedium`),
            for callers that need finer-grained data than the summary.

        Raises:
            ConfigurationError: if ``wifi_scheduling`` has no scheduler
                implementation, or any referenced file is malformed.
        """
        config = self.config
        horizon_ms = config.duration_s * 1000.0
        frame_groups = load_trace(config.wifi_trace_path)
        fg_by_id = {fg.fg_id: fg for fg in frame_groups}

        scheduler, optimal_statuses = _build_scheduler(config)
        medium = ChannelMedium()
        ctc = CTCChannel(
            per=config.ctc_per,
            delay_ms=config.ctc_delay_ms,
            max_retries=config.ctc_max_retries,
        )
        ap = APOrchestrator(
            ctc=ctc,
            scheduler=scheduler,
            d_sensing_ms=config.d_sensing_ms,
            optimal_statuses=optimal_statuses,
        )
        lwsa = LWSAAdapter()
        zc = ZigBeeCoordinator(lwsa=lwsa)
        stats = _RunStats()

        env = simpy.Environment()
        env.process(
            self._drive_cycles(
                env, config, frame_groups, fg_by_id, ap, zc, ctc, medium, stats
            )
        )
        env.run(until=horizon_ms)

        self.last_medium = medium
        return stats.finalize(medium, horizon_ms)

    def _drive_cycles(
        self,
        env: simpy.Environment,
        config: SimulationConfig,
        frame_groups: list[FrameGroup],
        fg_by_id: dict[int, FrameGroup],
        ap: APOrchestrator,
        zc: ZigBeeCoordinator,
        ctc: CTCChannel,
        medium: ChannelMedium,
        stats: _RunStats,
    ) -> simpy.events.ProcessGenerator:
        """SimPy process: advance from cycle to cycle, running one full
        AP/ZC/CTC/medium exchange at each cycle boundary."""
        horizon_ms = config.duration_s * 1000.0
        bidirectional = config.ctc_direction == "bidirectional"
        adaptive = config.zigbee_adaptation == "lwsa"

        for cycle in iter_cycles(frame_groups, config.zigbee_period_ms, horizon_ms):
            if env.now < cycle.start_ms:
                yield env.timeout(cycle.start_ms - env.now)

            zbeacon: CTCMessage | None = None
            if bidirectional:
                zbeacon = zc.build_zbeacon(
                    config.zigbee_pending_packets, cycle.start_ms
                )
                if ctc.delay_ms > 0:
                    yield env.timeout(ctc.delay_ms)

            outcome = ap.process_cycle(
                cycle.frame_groups,
                cycle.start_ms,
                cycle.end_ms,
                zbeacon,
                cycle.active_carryover,
            )
            if ctc.delay_ms > 0:
                yield env.timeout(ctc.delay_ms)
            stats.record_cycle(outcome)

            for decision in outcome.schedule.decisions:
                fg = fg_by_id[decision.fg_id]
                medium.register_transmission(
                    f"wifi-{cycle.index}-{decision.fg_id}",
                    "wifi",
                    decision.scheduled_start_ms,
                    fg.duration_ms,
                )

            if adaptive and outcome.wbeacon_delivered:
                fragments = _residual_wifi_fragments(
                    outcome.schedule,
                    fg_by_id,
                    outcome.schedule.t_free_start_ms,
                    outcome.schedule.t_free_end_ms,
                )
                superframe = zc.process_wbeacon(outcome.wbeacon, fragments)
            elif adaptive:
                # Handshake timeout exhausted (Issue #3): the ZC falls back
                # to uncoordinated CSMA/CA, i.e. the same WiFi-oblivious
                # legacy superframe as "fixed" adaptation, rather than
                # going dark for the cycle.
                stats.csma_ca_fallback_cycles += 1
                superframe = _fixed_superframe(cycle.start_ms)
            else:
                superframe = _fixed_superframe(cycle.start_ms)

            for packet in _synthesize_zigbee_packets(
                superframe, cycle.index, zc.lwsa.desired_packet_duration_ms
            ):
                stats.zigbee_packets_attempted += 1
                medium.register_transmission(
                    f"zigbee-{cycle.index}-{packet.packet_id}",
                    "zigbee",
                    packet.start_time_ms,
                    packet.duration_ms,
                )

            if env.now < cycle.end_ms:
                yield env.timeout(cycle.end_ms - env.now)

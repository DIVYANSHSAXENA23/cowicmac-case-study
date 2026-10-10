"""Integration tests for end-to-end coexistence scenarios."""

from pathlib import Path

import pytest

from cowic.exceptions import ConfigurationError
from cowic.sim.simulation_engine import SimulationConfig, SimulationEngine
from traces.synthetic_generator import generate_trace


@pytest.fixture
def short_trace(tmp_path: Path) -> Path:
    """A small trace (3 s) so tests run fast but cover several cycles."""
    trace_path = tmp_path / "short_trace.parquet"
    generate_trace(
        "configs/base_traffic1.yaml", duration_s=3.0, output_path=trace_path, seed=42
    )
    return trace_path


def test_simulation_engine_instantiation(short_trace: Path) -> None:
    """Verify SimulationEngine initialization with configuration dataclass."""
    config = SimulationConfig(
        scenario_name="Test_Exp4",
        duration_s=3.0,
        wifi_trace_path=short_trace,
        d_free_ms=62.0,
        d_sensing_ms=10.0,
        zigbee_period_ms=1000.0,
        random_seed=42,
    )
    engine = SimulationEngine(config)
    assert engine.config.scenario_name == "Test_Exp4"
    assert engine.config.random_seed == 42


def test_simulation_engine_run_matches_configured_duration(short_trace: Path) -> None:
    """Simulated duration always equals ``duration_s * 1000`` regardless of
    how many (or how few) scheduling cycles fit inside it."""
    config = SimulationConfig(
        scenario_name="Test_Exp4",
        duration_s=3.0,
        wifi_trace_path=short_trace,
        d_free_ms=62.0,
        d_sensing_ms=10.0,
        zigbee_period_ms=1000.0,
    )
    engine = SimulationEngine(config)
    result = engine.run()
    assert result["simulated_duration_ms"] == pytest.approx(3000.0)
    assert result["cycles_run"] == 3.0


def test_simulation_engine_milp_coexistence_protects_zigbee(short_trace: Path) -> None:
    """Exp 4 (MILP + L-WSA, bidirectional CTC) must achieve a near-perfect
    ZigBee success rate: the AP actively clears a window for it."""
    config = SimulationConfig(
        scenario_name="Test_Exp4",
        duration_s=3.0,
        wifi_trace_path=short_trace,
        d_free_ms=62.0,
        d_sensing_ms=10.0,
        zigbee_period_ms=1000.0,
        wifi_scheduling="milp_soft_constraint",
        ctc_direction="bidirectional",
        zigbee_adaptation="lwsa",
    )
    result = SimulationEngine(config).run()
    assert result["zigbee_transmissions"] > 0
    assert result["zigbee_success_rate"] > 0.9


def test_simulation_engine_uncoordinated_baseline_harms_zigbee(
    short_trace: Path,
) -> None:
    """Exp 1 (no coordination, fixed legacy ZigBee superframe) must show
    the coexistence problem: a much lower ZigBee success rate than the
    coordinated MILP+L-WSA scenario, since WiFi is never cleared for it."""
    config = SimulationConfig(
        scenario_name="Test_Exp1",
        duration_s=3.0,
        wifi_trace_path=short_trace,
        d_free_ms=62.0,
        d_sensing_ms=0.0,
        zigbee_period_ms=1000.0,
        wifi_scheduling="none",
        ctc_direction="none",
        zigbee_adaptation="fixed",
    )
    result = SimulationEngine(config).run()
    assert result["zigbee_transmissions"] > 0
    assert result["zigbee_success_rate"] < 0.5


@pytest.mark.parametrize(
    "wifi_scheduling,ctc_direction",
    [
        ("none", "none"),
        ("gap_search", "wifi_to_zigbee"),
        ("ecc_nav", "bidirectional"),
    ],
)
def test_simulation_engine_runs_all_baseline_schedulers(
    short_trace: Path, wifi_scheduling: str, ctc_direction: str
) -> None:
    """Every Exp 1-3 baseline scheduler runs to completion without error."""
    config = SimulationConfig(
        scenario_name=f"Test_{wifi_scheduling}",
        duration_s=3.0,
        wifi_trace_path=short_trace,
        d_free_ms=62.0,
        d_sensing_ms=0.0,
        zigbee_period_ms=1000.0,
        wifi_scheduling=wifi_scheduling,
        ctc_direction=ctc_direction,
        zigbee_adaptation="fixed",
    )
    result = SimulationEngine(config).run()
    assert result["cycles_run"] == 3.0
    assert result["wifi_transmissions"] > 0


def test_simulation_engine_rejects_unimplemented_hard_constraint_scheduler(
    short_trace: Path,
) -> None:
    """Exp 5's 'milp_hard_constraint' scheduler has no implementation yet;
    the engine must fail clearly rather than silently mis-scheduling."""
    config = SimulationConfig(
        scenario_name="Test_Exp5",
        duration_s=3.0,
        wifi_trace_path=short_trace,
        d_free_ms=62.0,
        d_sensing_ms=0.0,
        zigbee_period_ms=1000.0,
        wifi_scheduling="milp_hard_constraint",
    )
    with pytest.raises(ConfigurationError):
        SimulationEngine(config).run()


def test_simulation_engine_rejects_unknown_scheduler(short_trace: Path) -> None:
    config = SimulationConfig(
        scenario_name="Test_Unknown",
        duration_s=3.0,
        wifi_trace_path=short_trace,
        d_free_ms=62.0,
        d_sensing_ms=0.0,
        zigbee_period_ms=1000.0,
        wifi_scheduling="not_a_real_scheduler",
    )
    with pytest.raises(ConfigurationError):
        SimulationEngine(config).run()


def test_simulation_config_from_yaml_loads_exp1(tmp_path: Path) -> None:
    """from_yaml resolves the traffic profile, generates its trace on first
    use, and maps every yaml key onto SimulationConfig's field names."""
    config = SimulationConfig.from_yaml(
        Path("configs/exp1_uncoordinated.yaml"), trace_dir=tmp_path
    )
    assert config.scenario_name == "Exp_1"
    assert config.wifi_scheduling == "none"
    assert config.ctc_direction == "none"
    assert config.zigbee_adaptation == "fixed"
    assert config.d_sensing_ms == 0.0
    assert config.wifi_trace_path.exists()


def test_simulation_config_from_yaml_reuses_existing_trace(tmp_path: Path) -> None:
    """A second call with the same experiment/profile/seed does not
    regenerate the trace file (reuses it by path)."""
    config_1 = SimulationConfig.from_yaml(
        Path("configs/exp1_uncoordinated.yaml"), trace_dir=tmp_path
    )
    mtime_1 = config_1.wifi_trace_path.stat().st_mtime
    config_2 = SimulationConfig.from_yaml(
        Path("configs/exp1_uncoordinated.yaml"), trace_dir=tmp_path
    )
    mtime_2 = config_2.wifi_trace_path.stat().st_mtime
    assert config_1.wifi_trace_path == config_2.wifi_trace_path
    assert mtime_1 == mtime_2


def test_simulation_config_from_yaml_loads_exp4_milp_weights(tmp_path: Path) -> None:
    config = SimulationConfig.from_yaml(
        Path("configs/exp4_cowic_full.yaml"), trace_dir=tmp_path
    )
    assert config.wifi_scheduling == "milp_soft_constraint"
    assert config.gamma_sensing_weight == 10.0
    assert config.lambda_delay_weight == 1.0
    assert config.mu_base_cost == 100.0


def test_simulation_engine_exposes_raw_transmission_records(short_trace: Path) -> None:
    """After run(), raw per-transmission event records remain available
    via last_medium, beyond the summary dict's aggregates."""
    config = SimulationConfig(
        scenario_name="Test_Records",
        duration_s=3.0,
        wifi_trace_path=short_trace,
        d_free_ms=62.0,
        d_sensing_ms=10.0,
        zigbee_period_ms=1000.0,
        wifi_scheduling="milp_soft_constraint",
        ctc_direction="bidirectional",
        zigbee_adaptation="lwsa",
    )
    engine = SimulationEngine(config)
    assert engine.last_medium is None
    result = engine.run()
    assert engine.last_medium is not None
    assert len(engine.last_medium.transmissions) > 0
    total_records = len(engine.last_medium.transmissions)
    total_summary = int(result["wifi_transmissions"] + result["zigbee_transmissions"])
    assert total_records == total_summary


def test_simulation_engine_falls_back_to_csma_ca_on_total_ctc_loss(
    short_trace: Path,
) -> None:
    """When the CTC link always fails (per=1.0, no retries), the ZC must
    fall back to uncoordinated CSMA/CA (the fixed legacy superframe)
    rather than emit zero ZigBee activity for every cycle."""
    config = SimulationConfig(
        scenario_name="Test_CTCLoss",
        duration_s=3.0,
        wifi_trace_path=short_trace,
        d_free_ms=62.0,
        d_sensing_ms=10.0,
        zigbee_period_ms=1000.0,
        wifi_scheduling="milp_soft_constraint",
        ctc_direction="bidirectional",
        zigbee_adaptation="lwsa",
        ctc_per=1.0,
        ctc_max_retries=0,
    )
    result = SimulationEngine(config).run()
    assert result["wbeacon_lost"] == result["cycles_run"]
    assert result["csma_ca_fallback_cycles"] == result["cycles_run"]
    assert result["zigbee_packets_attempted"] > 0


def _fixed_baseline_config(
    trace: Path, wifi_scheduling: str, ctc_direction: str, **overrides: float
) -> SimulationConfig:
    return SimulationConfig(
        scenario_name=f"Test_{wifi_scheduling}",
        duration_s=3.0,
        wifi_trace_path=trace,
        d_free_ms=62.0,
        d_sensing_ms=0.0,
        zigbee_period_ms=1000.0,
        wifi_scheduling=wifi_scheduling,
        ctc_direction=ctc_direction,
        zigbee_adaptation="fixed",
        **overrides,  # type: ignore[arg-type]
    )


def _first_zigbee_start_per_cycle(engine: SimulationEngine) -> list[float]:
    assert engine.last_medium is not None
    starts: dict[int, float] = {}
    for record in engine.last_medium.transmissions:
        if record.protocol == "zigbee":
            cycle = int(record.start_time_ms // 1000.0)
            starts[cycle] = min(
                starts.get(cycle, record.start_time_ms), record.start_time_ms
            )
    return [starts[c] - c * 1000.0 for c in sorted(starts)]


def test_exp2_fixed_superframe_follows_announced_gap(short_trace: Path) -> None:
    """Exp 2 notifies ZigBee of the largest gap: the fixed superframe must
    start there, not at the cycle start, so Exp 2 differs from Exp 1."""
    exp1 = SimulationEngine(_fixed_baseline_config(short_trace, "none", "none"))
    exp2 = SimulationEngine(
        _fixed_baseline_config(short_trace, "gap_search", "wifi_to_zigbee")
    )
    r1, r2 = exp1.run(), exp2.run()

    beacon_slot = 0.96 * 4
    assert all(
        start == pytest.approx(beacon_slot)
        for start in _first_zigbee_start_per_cycle(exp1)
    )
    assert any(
        start > beacon_slot + 1e-6 for start in _first_zigbee_start_per_cycle(exp2)
    )
    assert r2["zigbee_success_count"] > r1["zigbee_success_count"]


def test_fixed_superframe_without_wbeacon_stays_at_cycle_start(
    short_trace: Path,
) -> None:
    """If the WBeacon never arrives, ZigBee has no window to follow."""
    lost = SimulationEngine(
        _fixed_baseline_config(
            short_trace, "gap_search", "wifi_to_zigbee", ctc_per=1.0, ctc_max_retries=0
        )
    )
    lost.run()
    assert all(
        start == pytest.approx(0.96 * 4)
        for start in _first_zigbee_start_per_cycle(lost)
    )


def test_exp6_without_zbeacon_still_serves_zigbee(short_trace: Path) -> None:
    """Exp 6 (MILP + L-WSA, WiFi->ZigBee CTC only) has no ZBeacon, so the AP
    must use the configured D_free instead of granting empty windows."""
    config = SimulationConfig(
        scenario_name="Test_Exp6",
        duration_s=3.0,
        wifi_trace_path=short_trace,
        d_free_ms=62.0,
        d_sensing_ms=0.0,
        zigbee_period_ms=1000.0,
        wifi_scheduling="milp_soft_constraint",
        ctc_direction="wifi_to_zigbee",
        zigbee_adaptation="lwsa",
    )
    result = SimulationEngine(config).run()
    assert result["zigbee_packets_attempted"] > 0
    assert result["zigbee_success_rate"] > 0.9

"""Integration tests for end-to-end coexistence scenarios."""

from pathlib import Path

import pytest

from cowic.sim.simulation_engine import SimulationConfig, SimulationEngine


def test_simulation_engine_instantiation() -> None:
    """Verify SimulationEngine initialization with configuration dataclass."""
    config = SimulationConfig(
        scenario_name="Test_Exp4",
        duration_s=1.0,
        wifi_trace_path=Path("traces/data/test.parquet"),
        d_free_ms=62.0,
        d_sensing_ms=10.0,
        zigbee_period_ms=1000.0,
        random_seed=42,
    )
    engine = SimulationEngine(config)
    assert engine.config.scenario_name == "Test_Exp4"
    assert engine.config.random_seed == 42


def test_simulation_engine_run_stub_raises() -> None:
    """Verify run raises NotImplementedError before implementation."""
    config = SimulationConfig(
        scenario_name="Test_Exp4",
        duration_s=1.0,
        wifi_trace_path=Path("traces/data/test.parquet"),
        d_free_ms=62.0,
        d_sensing_ms=10.0,
        zigbee_period_ms=1000.0,
    )
    engine = SimulationEngine(config)
    with pytest.raises(NotImplementedError):
        engine.run()

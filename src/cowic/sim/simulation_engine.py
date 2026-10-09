"""Discrete-event simulation engine powered by SimPy."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SimulationConfig:
    """Global parameters for an experiment run."""

    scenario_name: str
    duration_s: float
    wifi_trace_path: Path
    d_free_ms: float
    d_sensing_ms: float
    zigbee_period_ms: float
    random_seed: int = 42


class SimulationEngine:
    """Coordinates the SimPy discrete-event simulation environment."""

    def __init__(self, config: SimulationConfig) -> None:
        self.config = config

    def run(self) -> dict[str, float]:
        """Execute the discrete-event simulation scenario."""
        raise NotImplementedError(
            "SimulationEngine implementation planned for Sprint Day 2"
        )

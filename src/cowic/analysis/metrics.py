"""Metrics computation for coexistence evaluation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationMetrics:
    """Summary of performance indicators from a simulation run."""

    zigbee_gain_ratio: float
    wifi_drop_rate: float
    spectrum_utilization: float
    wifi_jitter_ms: float
    moved_fg_count: int
    max_fg_delay_ms: float


class MetricsCalculator:
    """Calculates throughput, drop rate, utilization, and delay statistics."""

    def compute(self, records: list[dict[str, float]]) -> SimulationMetrics:
        """Derive standard benchmark metrics from trace records."""
        raise NotImplementedError(
            "MetricsCalculator implementation planned for Sprint Day 2"
        )

"""WiFi Frame Group data structures."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FrameGroup:
    """Represents an aggregated burst of WiFi packets from a station."""

    fg_id: int
    arrival_time_ms: float
    duration_ms: float
    deadline_ms: float
    original_start_ms: float
    qos_sensitive: bool


@dataclass(frozen=True)
class SchedulingDecision:
    """Result of rescheduling a single Frame Group."""

    fg_id: int
    scheduled_start_ms: float
    is_postponed: bool
    delay_ms: float

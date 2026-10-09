"""Shared 2.4 GHz channel medium with collision detection."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TransmissionRecord:
    """Record of an airtime burst on the shared medium."""

    trans_id: str
    protocol: str
    start_time_ms: float
    end_time_ms: float
    success: bool


class ChannelMedium:
    """Detects temporal overlaps between concurrent transmissions."""

    def __init__(self) -> None:
        self.transmissions: list[TransmissionRecord] = []

    def register_transmission(
        self,
        trans_id: str,
        protocol: str,
        start_ms: float,
        duration_ms: float,
    ) -> TransmissionRecord:
        """Register a packet burst and evaluate collision state."""
        raise NotImplementedError(
            "ChannelMedium implementation planned for Sprint Day 1"
        )

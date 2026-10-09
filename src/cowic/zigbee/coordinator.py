"""ZigBee Coordinator state machine and demand manager."""

from enum import Enum, auto


class ZCState(Enum):
    """Operational states of the ZigBee Coordinator."""

    IDLE = auto()
    CTC_REPORTING = auto()
    COMMAND_ACQUISITION = auto()
    TRAFFIC_ADJUSTMENT = auto()
    SUPERFRAME_ACTIVE = auto()


class ZigBeeCoordinator:
    """Coordinates ZigBee nodes and interfaces with the WiFi AP via CTC."""

    def __init__(self, zc_id: str = "ZC_0") -> None:
        self.zc_id = zc_id
        self.state = ZCState.IDLE

    def generate_demand_report(self, pending_packets: int) -> float:
        """Calculate requested airtime duration based on pending queue."""
        raise NotImplementedError(
            "ZigBeeCoordinator demand reporting planned for Sprint Day 1"
        )

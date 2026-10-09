"""WiFi Access Point orchestrator state machine."""

from enum import Enum, auto

from cowic.models.frame_group import FrameGroup, SchedulingDecision


class APState(Enum):
    """Operational states of the WiFi Access Point orchestrator."""

    MAINTAINING = auto()
    CTC_GATHERING = auto()
    RESCHEDULING = auto()
    CTC_NOTIFYING = auto()
    TRANSMITTING = auto()


class APOrchestrator:
    """Manages the WiFi AP transmission queue and cross-technology coordination."""

    def __init__(self, ap_id: str = "AP_0") -> None:
        self.ap_id = ap_id
        self.state = APState.MAINTAINING

    def process_cycle(
        self,
        frame_groups: list[FrameGroup],
        d_free_ms: float,
        d_sensing_ms: float,
    ) -> list[SchedulingDecision]:
        """Execute one scheduling cycle at the AP."""
        raise NotImplementedError(
            "APOrchestrator implementation planned for Sprint Day 1"
        )

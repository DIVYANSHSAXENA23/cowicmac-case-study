"""MILP scheduler for WiFi Frame Groups."""

from dataclasses import dataclass

from cowic.models.frame_group import FrameGroup, SchedulingDecision


@dataclass(frozen=True)
class ScheduleResult:
    """Result of the MILP scheduling optimization."""

    decisions: list[SchedulingDecision]
    t_free_start_ms: float
    t_free_end_ms: float
    t_sense_start_ms: float
    t_sense_end_ms: float
    solver_status: str
    solve_time_ms: float


class MILPScheduler:
    """Solves the Frame Group rescheduling problem via PuLP."""

    def __init__(
        self,
        gamma: float = 10.0,
        lambda_weight: float = 1.0,
        mu_base: float = 100.0,
    ) -> None:
        self.gamma = gamma
        self.lambda_weight = lambda_weight
        self.mu_base = mu_base

    def schedule(
        self,
        frame_groups: list[FrameGroup],
        d_free_ms: float,
        d_sensing_ms: float,
        t_start_ms: float,
        t_end_ms: float,
    ) -> ScheduleResult:
        """Formulate and solve the MILP program."""
        raise NotImplementedError(
            "MILPScheduler implementation planned for Sprint Day 1"
        )

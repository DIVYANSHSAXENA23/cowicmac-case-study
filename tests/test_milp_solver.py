"""Unit tests for MILP scheduler."""

import pytest

from cowic.models.frame_group import FrameGroup
from cowic.wifi.milp_scheduler import MILPScheduler


def test_milp_scheduler_instantiation() -> None:
    """Verify MILPScheduler initialization with default weights."""
    scheduler = MILPScheduler(gamma=10.0, lambda_weight=1.0, mu_base=100.0)
    assert scheduler.gamma == 10.0
    assert scheduler.lambda_weight == 1.0


def test_milp_schedule_stub_raises() -> None:
    """Verify schedule method raises NotImplementedError before implementation."""
    scheduler = MILPScheduler()
    fgs = [
        FrameGroup(
            fg_id=1,
            arrival_time_ms=0.0,
            duration_ms=10.0,
            deadline_ms=100.0,
            original_start_ms=0.0,
            qos_sensitive=True,
        )
    ]
    with pytest.raises(NotImplementedError):
        scheduler.schedule(
            fgs,
            d_free_ms=30.0,
            d_sensing_ms=10.0,
            t_start_ms=0.0,
            t_end_ms=100.0,
        )

"""Unit tests for shared channel collision detection."""

import pytest

from cowic.sim.channel_medium import ChannelMedium


def test_channel_medium_instantiation() -> None:
    """Verify ChannelMedium starts with empty transmission log."""
    medium = ChannelMedium()
    assert len(medium.transmissions) == 0


def test_channel_medium_register_stub_raises() -> None:
    """Verify register_transmission raises NotImplementedError before implementation."""
    medium = ChannelMedium()
    with pytest.raises(NotImplementedError):
        medium.register_transmission(
            trans_id="TX_1",
            protocol="WiFi",
            start_ms=0.0,
            duration_ms=10.0,
        )

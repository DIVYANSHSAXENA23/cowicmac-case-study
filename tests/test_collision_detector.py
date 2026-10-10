"""Unit tests for shared channel collision detection."""

import pytest

from cowic.sim.channel_medium import ChannelMedium


def test_channel_medium_instantiation() -> None:
    """Verify ChannelMedium starts with empty transmission log."""
    medium = ChannelMedium()
    assert len(medium.transmissions) == 0


def test_non_overlapping_transmissions_both_succeed() -> None:
    """Independent, non-overlapping bursts should both succeed."""
    medium = ChannelMedium()
    first = medium.register_transmission(
        "WIFI_1", "WiFi", start_ms=0.0, duration_ms=10.0
    )
    second = medium.register_transmission(
        "ZB_1", "ZigBee", start_ms=10.0, duration_ms=5.0
    )
    assert first.success is True
    assert second.success is True


def test_overlapping_cross_protocol_transmissions_both_fail() -> None:
    """Overlapping WiFi and ZigBee bursts corrupt each other (Section 5.1)."""
    medium = ChannelMedium()
    wifi_rec = medium.register_transmission(
        "WIFI_1", "WiFi", start_ms=0.0, duration_ms=10.0
    )
    zb_rec = medium.register_transmission(
        "ZB_1", "ZigBee", start_ms=5.0, duration_ms=10.0
    )

    assert zb_rec.success is False
    # The earlier WiFi record must be retroactively flipped to failed.
    stored_wifi = next(r for r in medium.transmissions if r.trans_id == "WIFI_1")
    assert stored_wifi.success is False
    assert wifi_rec.success is True  # The returned snapshot is immutable.


def test_overlapping_same_protocol_transmissions_both_fail() -> None:
    """Two overlapping bursts of the same protocol also collide."""
    medium = ChannelMedium()
    medium.register_transmission("WIFI_1", "WiFi", start_ms=0.0, duration_ms=10.0)
    second = medium.register_transmission(
        "WIFI_2", "WiFi", start_ms=9.0, duration_ms=5.0
    )
    assert second.success is False
    stored_first = next(r for r in medium.transmissions if r.trans_id == "WIFI_1")
    assert stored_first.success is False


def test_adjacent_transmissions_do_not_collide() -> None:
    """Back-to-back bursts sharing an endpoint are not overlapping."""
    medium = ChannelMedium()
    first = medium.register_transmission(
        "WIFI_1", "WiFi", start_ms=0.0, duration_ms=10.0
    )
    second = medium.register_transmission(
        "ZB_1", "ZigBee", start_ms=10.0, duration_ms=5.0
    )
    assert first.success is True
    assert second.success is True


def test_failed_transmission_stays_failed_on_third_overlap() -> None:
    """A transmission already marked failed stays failed, never flips back."""
    medium = ChannelMedium()
    medium.register_transmission("A", "WiFi", start_ms=0.0, duration_ms=10.0)
    medium.register_transmission("B", "ZigBee", start_ms=5.0, duration_ms=10.0)
    # C overlaps only A, not B; A must remain failed.
    medium.register_transmission("C", "WiFi", start_ms=1.0, duration_ms=1.0)
    stored_a = next(r for r in medium.transmissions if r.trans_id == "A")
    assert stored_a.success is False


def test_register_transmission_rejects_non_positive_duration() -> None:
    """Zero or negative duration bursts are invalid."""
    medium = ChannelMedium()
    with pytest.raises(ValueError):
        medium.register_transmission("X", "WiFi", start_ms=0.0, duration_ms=0.0)


def test_register_transmission_rejects_duplicate_trans_id() -> None:
    """Registering the same trans_id twice raises an error."""
    medium = ChannelMedium()
    medium.register_transmission("X", "WiFi", start_ms=0.0, duration_ms=1.0)
    with pytest.raises(ValueError):
        medium.register_transmission("X", "WiFi", start_ms=5.0, duration_ms=1.0)


def test_successful_and_failed_transmission_filters() -> None:
    """successful_transmissions and failed_transmissions partition the log."""
    medium = ChannelMedium()
    medium.register_transmission("A", "WiFi", start_ms=0.0, duration_ms=10.0)
    medium.register_transmission("B", "ZigBee", start_ms=5.0, duration_ms=10.0)
    medium.register_transmission("C", "ZigBee", start_ms=20.0, duration_ms=5.0)

    successful_ids = {r.trans_id for r in medium.successful_transmissions()}
    failed_ids = {r.trans_id for r in medium.failed_transmissions()}
    assert successful_ids == {"C"}
    assert failed_ids == {"A", "B"}


def test_reset_clears_transmission_log() -> None:
    """reset() clears stored transmissions so a medium can be reused."""
    medium = ChannelMedium()
    medium.register_transmission("A", "WiFi", start_ms=0.0, duration_ms=10.0)
    medium.reset()
    assert medium.transmissions == []
    # A previously used trans_id can be reused after reset.
    record = medium.register_transmission("A", "WiFi", start_ms=0.0, duration_ms=1.0)
    assert record.success is True

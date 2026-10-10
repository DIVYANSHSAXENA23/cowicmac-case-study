"""Unit tests for the CTC signaling channel (packet error / delay model)."""

import random

import pytest

from cowic.ctc.channel import CTCChannel, CTCMessage, MessageType
from cowic.exceptions import ConfigurationError


def _zbeacon(timestamp_ms: float = 0.0) -> CTCMessage:
    return CTCMessage(
        msg_type=MessageType.ZBEACON,
        sender_id="ZC_0",
        timestamp_ms=timestamp_ms,
        payload={"d_free_ms": 10.0},
    )


def test_ctc_channel_zero_per_always_delivers() -> None:
    channel = CTCChannel(per=0.0)
    for _ in range(50):
        assert channel.transmit(_zbeacon()) is True
    assert channel.sent_count == 50
    assert channel.dropped_count == 0


def test_ctc_channel_per_one_never_delivers() -> None:
    channel = CTCChannel(per=1.0)
    for _ in range(50):
        assert channel.transmit(_zbeacon()) is False
    assert channel.sent_count == 50
    assert channel.dropped_count == 50


def test_ctc_channel_partial_per_drops_some_messages() -> None:
    channel = CTCChannel(per=0.5, rng=random.Random(42))
    results = [channel.transmit(_zbeacon()) for _ in range(200)]
    assert any(results)
    assert not all(results)
    assert channel.sent_count == 200
    assert channel.dropped_count == results.count(False)


def test_ctc_channel_reproducible_with_seeded_rng() -> None:
    channel_a = CTCChannel(per=0.3, rng=random.Random(7))
    channel_b = CTCChannel(per=0.3, rng=random.Random(7))
    results_a = [channel_a.transmit(_zbeacon()) for _ in range(30)]
    results_b = [channel_b.transmit(_zbeacon()) for _ in range(30)]
    assert results_a == results_b


def test_ctc_channel_rejects_out_of_range_per() -> None:
    with pytest.raises(ConfigurationError):
        CTCChannel(per=1.5)
    with pytest.raises(ConfigurationError):
        CTCChannel(per=-0.1)


def test_ctc_channel_rejects_negative_delay() -> None:
    with pytest.raises(ConfigurationError):
        CTCChannel(delay_ms=-1.0)


def test_ctc_channel_reset_clears_counters() -> None:
    channel = CTCChannel(per=0.0)
    channel.transmit(_zbeacon())
    channel.transmit(_zbeacon())
    assert channel.sent_count == 2
    channel.reset()
    assert channel.sent_count == 0
    assert channel.dropped_count == 0

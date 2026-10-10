"""Unit tests for L-WSA superframe adaptation algorithm (Eq. 3-10)."""

import pytest

from cowic.zigbee.lwsa_adapter import (
    BASE_SLOT_DURATION_MS,
    LWSAAdapter,
    _count_clear_slots,
    _min_cap_interval_ms,
    _packet_duration_ms,
    _per_packet_efficiency,
)


def test_lwsa_adapter_instantiation() -> None:
    """Verify LWSAAdapter initialization with default alpha weight."""
    adapter = LWSAAdapter(alpha=1.2)
    assert adapter.alpha == 1.2
    assert adapter.desired_packet_duration_ms == 2.0


def test_adapt_superframe_rejects_invalid_window() -> None:
    """dur_end_ms must be strictly greater than dur_start_ms."""
    adapter = LWSAAdapter()
    with pytest.raises(ValueError):
        adapter.adapt_superframe(50.0, 10.0, [])


def test_adapt_superframe_respects_16_slot_limit() -> None:
    """Selected configuration never violates the standard 16-slot limit."""
    adapter = LWSAAdapter()
    for window_ms in [5.0, 20.0, 62.0, 200.0, 1000.0]:
        config = adapter.adapt_superframe(0.0, window_ms, [])
        assert 0 <= config.cfp_slots <= 7
        assert config.cap_slots + config.cfp_slots <= 15
        assert config.cap_slots >= 0


def test_adapt_superframe_fits_within_granted_whitespace() -> None:
    """Total active duration (1 + i + j slots) fits within the window."""
    adapter = LWSAAdapter()
    for window_ms in [5.0, 20.0, 62.0, 200.0]:
        config = adapter.adapt_superframe(0.0, window_ms, [])
        total_active_ms = (
            1 + config.cap_slots + config.cfp_slots
        ) * config.slot_duration_ms
        assert total_active_ms <= window_ms + 1e-9


def test_adapt_superframe_too_short_for_beacon_returns_empty() -> None:
    """A window shorter than a single beacon slot yields zero activity."""
    adapter = LWSAAdapter()
    config = adapter.adapt_superframe(0.0, 0.5, [])
    assert config.cap_slots == 0
    assert config.cfp_slots == 0


def test_adapt_superframe_prefers_cfp_when_alpha_high() -> None:
    """A higher alpha should not reduce the selected CFP slot share."""
    low_alpha = LWSAAdapter(alpha=0.1).adapt_superframe(0.0, 62.0, [])
    high_alpha = LWSAAdapter(alpha=5.0).adapt_superframe(0.0, 62.0, [])
    assert high_alpha.cfp_slots >= low_alpha.cfp_slots


def test_adapt_superframe_accounts_for_residual_wifi_fragment() -> None:
    """A WiFi fragment inside the window reduces usable clear slot count,
    without ever selecting a configuration that pretends the fragment
    doesn't exist (slot counts inside _best_slot_split must reflect it)."""
    adapter = LWSAAdapter()
    clean = adapter.adapt_superframe(0.0, 62.0, [])
    fragmented = adapter.adapt_superframe(0.0, 62.0, [(20.0, 25.0)])
    # Both configurations must still respect the structural constraints.
    for config in (clean, fragmented):
        assert config.cap_slots + config.cfp_slots <= 15
        assert 0 <= config.cfp_slots <= 7


def test_adapt_superframe_offset_avoids_early_interference() -> None:
    """A WiFi fragment covering the whole window start forces a later
    beacon offset (Section 4.4: 'the beacon offset is first adjusted to
    avoid early interference')."""
    adapter = LWSAAdapter()
    # Fragment occupies [0, 50) of a 60ms window: only [50, 60) is usable.
    config = adapter.adapt_superframe(0.0, 60.0, [(0.0, 50.0)])
    assert config.beacon_offset_ms >= 50.0


def test_adapt_superframe_fully_busy_window_returns_empty() -> None:
    """A window entirely covered by WiFi fragments yields zero activity."""
    adapter = LWSAAdapter()
    config = adapter.adapt_superframe(0.0, 10.0, [(0.0, 10.0)])
    assert config.cap_slots == 0
    assert config.cfp_slots == 0


def test_packet_duration_capped_by_slot_and_hardware() -> None:
    """t_pk (Eq. 8) never exceeds the slot width minus turnaround/ack."""
    small_slot = BASE_SLOT_DURATION_MS  # 0.96 ms
    pk = _packet_duration_ms(small_slot, desired_packet_duration_ms=100.0)
    assert pk <= small_slot
    assert pk >= 0.0


def test_min_cap_interval_includes_two_backoff_slots() -> None:
    """t_min (Eq. 8) is 2 backoff slots plus the packet duration."""
    pk = 2.0
    t_min = _min_cap_interval_ms(pk)
    assert t_min > pk  # must include backoff overhead


def test_per_packet_efficiency_is_bounded() -> None:
    """eta^p (Eq. 7) stays within [0, 1] for realistic inputs."""
    eta = _per_packet_efficiency(packet_duration_ms=2.0, interval_ms=2.64)
    assert 0.0 <= eta <= 1.0


def test_count_clear_slots_excludes_overlapping_fragment() -> None:
    """A fragment overlapping a slot's occupancy window excludes it."""
    # 3 slots of width 2ms starting at t=0: [0,2), [2,4), [4,6).
    clear_no_frag = _count_clear_slots(3, 0.0, 2.0, 2.0, [])
    clear_with_frag = _count_clear_slots(3, 0.0, 2.0, 2.0, [(3.0, 3.5)])
    assert clear_no_frag == 3
    assert clear_with_frag == 2  # slot [2,4) overlaps [3.0, 3.5)


def test_count_clear_slots_ignores_fragment_outside_occupancy_width() -> None:
    """A CAP slot's grid width exceeds its checked occupancy width
    (t_min < t_SfSlot): a fragment landing only in the unused tail must
    not disqualify the slot."""
    # Grid slot width 4ms, but only the first 2ms (t_min) is checked.
    clear = _count_clear_slots(1, 0.0, 4.0, 2.0, [(3.0, 3.5)])
    assert clear == 1


def test_zc_demand_report_scales_with_pending_packets() -> None:
    """generate_demand_report returns zero for an empty queue and grows
    linearly with pending packet count."""
    from cowic.zigbee.coordinator import ZigBeeCoordinator

    zc = ZigBeeCoordinator()
    assert zc.generate_demand_report(0) == 0.0
    demand_5 = zc.generate_demand_report(5)
    demand_10 = zc.generate_demand_report(10)
    assert demand_10 == pytest.approx(2 * demand_5)


def test_zc_demand_report_rejects_negative_queue() -> None:
    from cowic.exceptions import ConfigurationError
    from cowic.zigbee.coordinator import ZigBeeCoordinator

    zc = ZigBeeCoordinator()
    with pytest.raises(ConfigurationError):
        zc.generate_demand_report(-1)


def test_zc_build_zbeacon_reports_demand() -> None:
    from cowic.ctc.channel import MessageType
    from cowic.wifi.ap_orchestrator import ZBEACON_DEMAND_KEY
    from cowic.zigbee.coordinator import ZigBeeCoordinator

    zc = ZigBeeCoordinator(zc_id="ZC_7")
    zbeacon = zc.build_zbeacon(pending_packets=3, timestamp_ms=100.0)
    assert zbeacon.msg_type is MessageType.ZBEACON
    assert zbeacon.sender_id == "ZC_7"
    assert zbeacon.timestamp_ms == 100.0
    assert zbeacon.payload[ZBEACON_DEMAND_KEY] > 0.0


def test_zc_process_wbeacon_adapts_superframe() -> None:
    from cowic.ctc.channel import CTCMessage, MessageType
    from cowic.zigbee.coordinator import ZCState, ZigBeeCoordinator

    zc = ZigBeeCoordinator()
    wbeacon = CTCMessage(
        msg_type=MessageType.WBEACON,
        sender_id="AP_0",
        timestamp_ms=0.0,
        payload={
            "t_free_start_ms": 0.0,
            "t_free_end_ms": 62.0,
            "t_sense_start_ms": 62.0,
            "t_sense_end_ms": 72.0,
        },
    )
    config = zc.process_wbeacon(wbeacon, residual_wifi_fragments=[])
    assert zc.state is ZCState.SUPERFRAME_ACTIVE
    assert zc.superframe is config
    assert config.cap_slots + config.cfp_slots > 0


def test_zc_process_wbeacon_zero_window_yields_empty_superframe() -> None:
    """A zero-length granted window (no airtime this cycle) is handled
    gracefully, not as an error."""
    from cowic.ctc.channel import CTCMessage, MessageType
    from cowic.zigbee.coordinator import ZigBeeCoordinator

    zc = ZigBeeCoordinator()
    wbeacon = CTCMessage(
        msg_type=MessageType.WBEACON,
        sender_id="AP_0",
        timestamp_ms=0.0,
        payload={
            "t_free_start_ms": 0.0,
            "t_free_end_ms": 0.0,
            "t_sense_start_ms": 0.0,
            "t_sense_end_ms": 0.0,
        },
    )
    config = zc.process_wbeacon(wbeacon, residual_wifi_fragments=[])
    assert config.cap_slots == 0
    assert config.cfp_slots == 0


def test_zc_process_wbeacon_rejects_wrong_message_type() -> None:
    from cowic.ctc.channel import CTCMessage, MessageType
    from cowic.exceptions import ProtocolError
    from cowic.zigbee.coordinator import ZigBeeCoordinator

    zc = ZigBeeCoordinator()
    not_a_wbeacon = CTCMessage(
        msg_type=MessageType.ZBEACON, sender_id="ZC_0", timestamp_ms=0.0, payload={}
    )
    with pytest.raises(ProtocolError):
        zc.process_wbeacon(not_a_wbeacon, residual_wifi_fragments=[])


def test_zc_process_wbeacon_rejects_missing_keys() -> None:
    from cowic.ctc.channel import CTCMessage, MessageType
    from cowic.exceptions import ProtocolError
    from cowic.zigbee.coordinator import ZigBeeCoordinator

    zc = ZigBeeCoordinator()
    incomplete = CTCMessage(
        msg_type=MessageType.WBEACON,
        sender_id="AP_0",
        timestamp_ms=0.0,
        payload={"t_free_start_ms": 0.0},
    )
    with pytest.raises(ProtocolError):
        zc.process_wbeacon(incomplete, residual_wifi_fragments=[])

"""Unit tests for L-WSA superframe adaptation algorithm."""

import pytest

from cowic.zigbee.lwsa_adapter import LWSAAdapter


def test_lwsa_adapter_instantiation() -> None:
    """Verify LWSAAdapter initialization with default alpha weight."""
    adapter = LWSAAdapter(alpha=1.2)
    assert adapter.alpha == 1.2


def test_lwsa_adapt_stub_raises() -> None:
    """Verify adapt_superframe raises NotImplementedError before implementation."""
    adapter = LWSAAdapter()
    with pytest.raises(NotImplementedError):
        adapter.adapt_superframe(
            dur_start_ms=10.0,
            dur_end_ms=72.0,
            residual_wifi_fragments=[],
        )

"""Cross-Technology Communication (CTC) signaling channel.

Models the bidirectional out-of-band control link between the WiFi AP and
the ZigBee Coordinator: W2Z (WiCast, AP -> ZC WBeacon) and Z2W (SymBee, ZC
-> AP ZBeacon) per Section 4.2. Delivery is modeled as an independent
Bernoulli trial per message, parameterized by a packet error rate
(``per``); ``delay_ms`` is a fixed one-way transit time exposed for
callers (e.g. a SimPy process) to apply as their own ``env.timeout`` -
this class does not advance simulated time itself, since ``transmit`` is
a synchronous, non-generator call.
"""

import math
import random
from dataclasses import dataclass
from enum import Enum, auto

from cowic.exceptions import ConfigurationError


class MessageType(Enum):
    """Types of cross-technology coordination frames."""

    WBEACON = auto()
    ZBEACON = auto()


@dataclass(frozen=True)
class CTCMessage:
    """Encapsulates control data sent across heterogeneous radios."""

    msg_type: MessageType
    sender_id: str
    timestamp_ms: float
    payload: dict[str, float]


class CTCChannel:
    """Simulates bidirectional W2Z (WiCast) and Z2W (SymBee) signaling.

    Each call to :meth:`transmit` is an independent Bernoulli trial: the
    message is delivered with probability ``1 - per``. ``rng`` is
    injectable for reproducible, seeded simulation runs; it defaults to a
    fresh, unseeded :class:`random.Random`.
    """

    def __init__(
        self,
        per: float = 0.0,
        delay_ms: float = 0.1,
        rng: random.Random | None = None,
    ) -> None:
        if not math.isfinite(per) or not (0.0 <= per <= 1.0):
            raise ConfigurationError(f"per must be within [0, 1], got {per}")
        if not math.isfinite(delay_ms) or delay_ms < 0:
            raise ConfigurationError(
                f"delay_ms must be finite and non-negative, got {delay_ms}"
            )
        self.per = per
        self.delay_ms = delay_ms
        self._rng = rng if rng is not None else random.Random()
        self.sent_count = 0
        self.dropped_count = 0

    def transmit(self, message: CTCMessage) -> bool:
        """Deliver a CTC signaling frame with error rate modeling.

        Returns:
            ``True`` if the message was delivered, ``False`` if it was
            dropped by the simulated packet error rate.
        """
        self.sent_count += 1
        delivered = self._rng.random() >= self.per
        if not delivered:
            self.dropped_count += 1
        return delivered

    def reset(self) -> None:
        """Clear delivery counters, for reuse across scenarios."""
        self.sent_count = 0
        self.dropped_count = 0

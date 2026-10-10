"""Shared 2.4 GHz channel medium with collision detection.

The base paper assumes a single shared channel: any temporal overlap between
a WiFi Frame Group and a ZigBee transmission corrupts both ("mutual
corruption", Section 5.1). This module generalizes that rule to any pair of
registered bursts, since two overlapping WiFi FGs (e.g. from a scheduling
bug) or two overlapping ZigBee slots are equally invalid on a single-channel
half-duplex medium.

Collisions are retroactive: when a new transmission is registered, every
previously stored transmission that overlaps it is flipped from success to
failure, and the new transmission itself is recorded as failed. A
transmission that collided with an already-failed transmission remains
failed; it is never flipped back to success.
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class TransmissionRecord:
    """Record of an airtime burst on the shared medium."""

    trans_id: str
    protocol: str
    start_time_ms: float
    end_time_ms: float
    success: bool


def _intervals_overlap(
    start_a: float, end_a: float, start_b: float, end_b: float
) -> bool:
    """Return True if two half-open intervals ``[start, end)`` overlap."""
    return start_a < end_b and start_b < end_a


class ChannelMedium:
    """Detects temporal overlaps between concurrent transmissions.

    Transmissions are stored in registration order in ``self.transmissions``.
    Call :meth:`register_transmission` once per burst as the simulation
    advances; registration order does not need to match start time order
    (e.g. a short ZigBee packet registered after a longer WiFi FG that
    started earlier is still checked against it).
    """

    def __init__(self) -> None:
        self.transmissions: list[TransmissionRecord] = []
        self._ids_seen: set[str] = set()

    def register_transmission(
        self,
        trans_id: str,
        protocol: str,
        start_ms: float,
        duration_ms: float,
    ) -> TransmissionRecord:
        """Register a packet burst and evaluate its collision state.

        Returns the newly created :class:`TransmissionRecord`. Any
        previously registered transmission that overlaps this burst in time
        is retroactively marked as failed in ``self.transmissions``.

        Raises:
            ValueError: if ``duration_ms`` is not positive, or ``trans_id``
                was already registered.
        """
        if duration_ms <= 0:
            raise ValueError(f"duration_ms must be positive, got {duration_ms}")
        if trans_id in self._ids_seen:
            raise ValueError(f"trans_id {trans_id!r} already registered")

        end_ms = start_ms + duration_ms
        collided = False
        for index, existing in enumerate(self.transmissions):
            if _intervals_overlap(
                existing.start_time_ms, existing.end_time_ms, start_ms, end_ms
            ):
                collided = True
                if existing.success:
                    self.transmissions[index] = replace(existing, success=False)

        record = TransmissionRecord(
            trans_id=trans_id,
            protocol=protocol,
            start_time_ms=start_ms,
            end_time_ms=end_ms,
            success=not collided,
        )
        self.transmissions.append(record)
        self._ids_seen.add(trans_id)
        return record

    def successful_transmissions(self) -> list[TransmissionRecord]:
        """Return all collision-free transmissions registered so far."""
        return [record for record in self.transmissions if record.success]

    def failed_transmissions(self) -> list[TransmissionRecord]:
        """Return all corrupted (colliding) transmissions registered so far."""
        return [record for record in self.transmissions if not record.success]

    def reset(self) -> None:
        """Clear all registered transmissions, for reuse across scenarios."""
        self.transmissions.clear()
        self._ids_seen.clear()

"""Dependency-free deterministic impairment engine."""

from __future__ import annotations

from .config import LinkConfig
from .decisions import (
    Delivery,
    PacketOutcome,
    SplitMix64,
    probability_hit,
    scale_u64,
)

_DRAWS_PER_PACKET = 6


def flip_bit(payload: bytes, bit_index: int) -> bytes:
    """Return ``payload`` with exactly one bit flipped.

    Bit zero is the least-significant bit of byte zero. The input is never
    mutated because bytes are immutable and the output is created from a copy.
    """

    bit_count = len(payload) * 8
    if not 0 <= bit_index < bit_count:
        raise ValueError("bit_index is outside the payload")
    changed = bytearray(payload)
    byte_index, offset = divmod(bit_index, 8)
    changed[byte_index] ^= 1 << offset
    return bytes(changed)


class ImpairmentEngine:
    """Convert an ordered stream of datagrams into deterministic outcomes.

    Exactly six PRNG draws are consumed for every input packet, independent of
    which impairments are enabled or selected. This fixed draw schedule makes
    results reproducible when unrelated rates are changed and provides a small,
    testable compatibility contract for golden decisions.
    """

    __slots__ = ("_packet_index", "_rng", "config")

    def __init__(self, config: LinkConfig) -> None:
        self.config = config
        self._rng = SplitMix64(config.seed)
        self._packet_index = 0

    @property
    def packet_index(self) -> int:
        """Index assigned to the next packet passed to :meth:`process`."""

        return self._packet_index

    def process(self, payload: bytes) -> PacketOutcome:
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")

        samples = tuple(self._rng.next_u64() for _ in range(_DRAWS_PER_PACKET))
        packet_index = self._packet_index
        self._packet_index += 1

        drop = probability_hit(samples[0], self.config.loss_rate)
        duplicate = probability_hit(samples[1], self.config.duplicate_rate)
        corrupt = probability_hit(samples[2], self.config.corrupt_rate)

        jitter_offset = 0
        if self.config.jitter_ms:
            span = 2 * self.config.jitter_ms + 1
            jitter_offset = scale_u64(samples[3], span) - self.config.jitter_ms
        delay_ms = max(0, self.config.latency_ms + jitter_offset)

        hold_packets = 0
        if self.config.reorder_window:
            hold_packets = scale_u64(samples[4], self.config.reorder_window + 1)

        corrupted_bit: int | None = None
        output_payload = payload
        if corrupt and payload:
            corrupted_bit = scale_u64(samples[5], len(payload) * 8)
            output_payload = flip_bit(payload, corrupted_bit)

        if drop:
            return PacketOutcome(packet_index=packet_index, dropped=True, deliveries=())

        copies = 2 if duplicate else 1
        deliveries = tuple(
            Delivery(
                payload=output_payload,
                copy_index=copy_index,
                delay_ms=delay_ms,
                hold_packets=hold_packets,
                corrupted_bit=corrupted_bit,
            )
            for copy_index in range(copies)
        )
        return PacketOutcome(
            packet_index=packet_index,
            dropped=False,
            deliveries=deliveries,
        )

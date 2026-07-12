"""Stable decision types and pseudo-random primitives for link impairments."""

from __future__ import annotations

from dataclasses import dataclass

_MASK_64 = (1 << 64) - 1
_UNIT_64 = 1 << 64
_GOLDEN_GAMMA = 0x9E3779B97F4A7C15
_MIX_1 = 0xBF58476D1CE4E5B9
_MIX_2 = 0x94D049BB133111EB


class SplitMix64:
    """Small, explicitly specified 64-bit generator.

    The algorithm is kept inside OrbitOps rather than delegating the public
    deterministic contract to implementation details of :mod:`random`.
    """

    __slots__ = ("_state",)

    def __init__(self, seed: int) -> None:
        self._state = seed & _MASK_64

    def next_u64(self) -> int:
        self._state = (self._state + _GOLDEN_GAMMA) & _MASK_64
        value = self._state
        value = ((value ^ (value >> 30)) * _MIX_1) & _MASK_64
        value = ((value ^ (value >> 27)) * _MIX_2) & _MASK_64
        return (value ^ (value >> 31)) & _MASK_64


def probability_hit(sample: int, rate: float) -> bool:
    """Map one 64-bit sample to a deterministic probability decision."""

    if rate <= 0.0:
        return False
    if rate >= 1.0:
        return True
    numerator, denominator = float(rate).as_integer_ratio()
    threshold = (numerator * _UNIT_64) // denominator
    return sample < threshold


def scale_u64(sample: int, upper_bound: int) -> int:
    """Scale one 64-bit sample into ``range(upper_bound)`` using multiply-high."""

    if upper_bound <= 0:
        raise ValueError("upper_bound must be positive")
    return (sample * upper_bound) >> 64


@dataclass(frozen=True, slots=True)
class Delivery:
    """One datagram that a future runtime must eventually emit."""

    payload: bytes
    copy_index: int
    delay_ms: int
    hold_packets: int
    corrupted_bit: int | None


@dataclass(frozen=True, slots=True)
class PacketOutcome:
    """Deterministic result for one input datagram."""

    packet_index: int
    dropped: bool
    deliveries: tuple[Delivery, ...]

    @property
    def duplicated(self) -> bool:
        return len(self.deliveries) == 2

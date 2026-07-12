"""Deterministic link-impairment primitives for OrbitOps."""

from .config import LinkConfig
from .decisions import Delivery, PacketOutcome
from .impairments import ImpairmentEngine, flip_bit

__all__ = [
    "Delivery",
    "ImpairmentEngine",
    "LinkConfig",
    "PacketOutcome",
    "flip_bit",
]

"""Validated configuration for the deterministic OrbitOps link emulator."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real

_MAX_SEED = (1 << 64) - 1
_MAX_REORDER_WINDOW = 65_535


def _validate_rate(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")


def _validate_non_negative_int(name: str, value: int, *, maximum: int | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}")


@dataclass(frozen=True, slots=True)
class LinkConfig:
    """Pure impairment-engine configuration.

    Rates are probabilities in the inclusive range ``[0.0, 1.0]``. Delay values
    are expressed in milliseconds. ``reorder_window`` is the maximum number of
    subsequently received packets by which one packet may be held.
    """

    seed: int = 0
    loss_rate: float = 0.0
    duplicate_rate: float = 0.0
    corrupt_rate: float = 0.0
    latency_ms: int = 0
    jitter_ms: int = 0
    reorder_window: int = 0

    def __post_init__(self) -> None:
        _validate_non_negative_int("seed", self.seed, maximum=_MAX_SEED)
        _validate_rate("loss_rate", self.loss_rate)
        _validate_rate("duplicate_rate", self.duplicate_rate)
        _validate_rate("corrupt_rate", self.corrupt_rate)
        _validate_non_negative_int("latency_ms", self.latency_ms)
        _validate_non_negative_int("jitter_ms", self.jitter_ms)
        _validate_non_negative_int(
            "reorder_window",
            self.reorder_window,
            maximum=_MAX_REORDER_WINDOW,
        )

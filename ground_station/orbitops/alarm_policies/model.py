"""Immutable alarm-policy model and validation rules."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

ALARM_POLICY_SCHEMA_VERSION = 1
_MAX_POLICY_NAME_LENGTH = 64
_MAX_DESCRIPTION_LENGTH = 500
_POLICY_NAME_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")


def _finite_float(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


@dataclass(frozen=True, slots=True)
class TemperatureAlarmPolicy:
    """Temperature thresholds and shared high-temperature hysteresis in °C."""

    warning_c: float
    critical_c: float
    hysteresis_c: float

    def __post_init__(self) -> None:
        warning_c = _finite_float("temperature.warning_c", self.warning_c)
        critical_c = _finite_float("temperature.critical_c", self.critical_c)
        hysteresis_c = _finite_float("temperature.hysteresis_c", self.hysteresis_c)
        if warning_c >= critical_c:
            raise ValueError("temperature.warning_c must be less than temperature.critical_c")
        if hysteresis_c < 0.0:
            raise ValueError("temperature.hysteresis_c must be non-negative")
        warning_clear_c = warning_c - hysteresis_c
        critical_clear_c = critical_c - hysteresis_c
        if not math.isfinite(warning_clear_c) or not math.isfinite(critical_clear_c):
            raise ValueError("temperature clear thresholds must be finite")
        if critical_clear_c < warning_c:
            raise ValueError(
                "temperature critical clear threshold must not fall below temperature.warning_c"
            )
        object.__setattr__(self, "warning_c", warning_c)
        object.__setattr__(self, "critical_c", critical_c)
        object.__setattr__(self, "hysteresis_c", hysteresis_c)


@dataclass(frozen=True, slots=True)
class BatteryAlarmPolicy:
    """Low-battery critical threshold and recovery hysteresis in volts."""

    critical_v: float
    hysteresis_v: float

    def __post_init__(self) -> None:
        critical_v = _finite_float("battery.critical_v", self.critical_v)
        hysteresis_v = _finite_float("battery.hysteresis_v", self.hysteresis_v)
        if critical_v <= 0.0:
            raise ValueError("battery.critical_v must be positive")
        if hysteresis_v < 0.0:
            raise ValueError("battery.hysteresis_v must be non-negative")
        if not math.isfinite(critical_v + hysteresis_v):
            raise ValueError("battery clear threshold must be finite")
        object.__setattr__(self, "critical_v", critical_v)
        object.__setattr__(self, "hysteresis_v", hysteresis_v)


@dataclass(frozen=True, slots=True)
class ModeAlarmPolicy:
    """Spacecraft-mode alarm enablement."""

    alarm_on_safe: bool

    def __post_init__(self) -> None:
        if not isinstance(self.alarm_on_safe, bool):
            raise TypeError("mode.alarm_on_safe must be a boolean")


@dataclass(frozen=True, slots=True)
class SequenceAlarmPolicy:
    """Sequence-integrity alarm enablement."""

    detect_gaps: bool

    def __post_init__(self) -> None:
        if not isinstance(self.detect_gaps, bool):
            raise TypeError("sequence.detect_gaps must be a boolean")


@dataclass(frozen=True, slots=True)
class AlarmPolicy:
    """Validated, immutable alarm-policy definition."""

    schema_version: int
    name: str
    description: str | None
    temperature: TemperatureAlarmPolicy
    battery: BatteryAlarmPolicy
    mode: ModeAlarmPolicy
    sequence: SequenceAlarmPolicy

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("schema_version must be an integer")
        if self.schema_version != ALARM_POLICY_SCHEMA_VERSION:
            raise ValueError(
                "unsupported schema_version "
                f"{self.schema_version}; expected {ALARM_POLICY_SCHEMA_VERSION}"
            )
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if (
            len(self.name) > _MAX_POLICY_NAME_LENGTH
            or _POLICY_NAME_PATTERN.fullmatch(self.name) is None
        ):
            raise ValueError(
                "name must be a lowercase slug of 1 to 64 characters using letters, digits, and "
                "hyphens; hyphens may not be leading or trailing"
            )
        if self.description is not None:
            if not isinstance(self.description, str):
                raise TypeError("description must be a string or None")
            if not self.description:
                raise ValueError("description must not be empty when provided")
            if len(self.description) > _MAX_DESCRIPTION_LENGTH:
                raise ValueError(
                    f"description must be at most {_MAX_DESCRIPTION_LENGTH} characters"
                )
            if "\x00" in self.description:
                raise ValueError("description must not contain NUL characters")
        if not isinstance(self.temperature, TemperatureAlarmPolicy):
            raise TypeError("temperature must be a TemperatureAlarmPolicy instance")
        if not isinstance(self.battery, BatteryAlarmPolicy):
            raise TypeError("battery must be a BatteryAlarmPolicy instance")
        if not isinstance(self.mode, ModeAlarmPolicy):
            raise TypeError("mode must be a ModeAlarmPolicy instance")
        if not isinstance(self.sequence, SequenceAlarmPolicy):
            raise TypeError("sequence must be a SequenceAlarmPolicy instance")

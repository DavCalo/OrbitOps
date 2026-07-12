"""Strict TOML parser for OrbitOps alarm policies."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping

from .errors import AlarmPolicyParseError, AlarmPolicyValidationError
from .model import (
    AlarmPolicy,
    BatteryAlarmPolicy,
    ModeAlarmPolicy,
    SequenceAlarmPolicy,
    TemperatureAlarmPolicy,
)

_TOP_LEVEL_KEYS = frozenset(
    {"schema_version", "name", "description", "temperature", "battery", "mode", "sequence"}
)
_REQUIRED_TOP_LEVEL_KEYS = frozenset(
    {"schema_version", "name", "temperature", "battery", "mode", "sequence"}
)
_SECTION_KEYS = {
    "temperature": frozenset({"warning_c", "critical_c", "hysteresis_c"}),
    "battery": frozenset({"critical_v", "hysteresis_v"}),
    "mode": frozenset({"alarm_on_safe"}),
    "sequence": frozenset({"detect_gaps"}),
}


def _format_keys(keys: set[str] | frozenset[str]) -> str:
    return ", ".join(sorted(keys))


def _validate_keys(
    table: Mapping[str, object],
    *,
    expected: frozenset[str],
    source: str,
    section: str,
) -> None:
    unknown = set(table) - expected
    if unknown:
        raise AlarmPolicyValidationError(
            f"{source}: unknown {section} key(s): {_format_keys(unknown)}"
        )
    missing = expected - set(table)
    if missing:
        raise AlarmPolicyValidationError(
            f"{source}: missing required {section} key(s): {_format_keys(missing)}"
        )


def _require_table(
    document: Mapping[str, object],
    key: str,
    *,
    source: str,
) -> Mapping[str, object]:
    value = document[key]
    if not isinstance(value, dict):
        raise AlarmPolicyValidationError(f"{source}: {key} must be a TOML table")
    table: Mapping[str, object] = value
    _validate_keys(table, expected=_SECTION_KEYS[key], source=source, section=key)
    return table


def _require_string(table: Mapping[str, object], key: str) -> str:
    value = table[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _read_optional_string(table: Mapping[str, object], key: str) -> str | None:
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _require_int(table: Mapping[str, object], key: str) -> int:
    value = table[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value


def _require_real(table: Mapping[str, object], section: str, key: str) -> float:
    value = table[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{section}.{key} must be a real number")
    return float(value)


def _require_bool(table: Mapping[str, object], section: str, key: str) -> bool:
    value = table[key]
    if not isinstance(value, bool):
        raise TypeError(f"{section}.{key} must be a boolean")
    return value


def _policy_from_mapping(
    document: Mapping[str, object],
    *,
    source: str,
) -> AlarmPolicy:
    unknown_top_level = set(document) - _TOP_LEVEL_KEYS
    if unknown_top_level:
        raise AlarmPolicyValidationError(
            f"{source}: unknown top-level key(s): {_format_keys(unknown_top_level)}"
        )
    missing = _REQUIRED_TOP_LEVEL_KEYS - set(document)
    if missing:
        raise AlarmPolicyValidationError(
            f"{source}: missing required key(s): {_format_keys(missing)}"
        )

    temperature = _require_table(document, "temperature", source=source)
    battery = _require_table(document, "battery", source=source)
    mode = _require_table(document, "mode", source=source)
    sequence = _require_table(document, "sequence", source=source)

    try:
        return AlarmPolicy(
            schema_version=_require_int(document, "schema_version"),
            name=_require_string(document, "name"),
            description=_read_optional_string(document, "description"),
            temperature=TemperatureAlarmPolicy(
                warning_c=_require_real(temperature, "temperature", "warning_c"),
                critical_c=_require_real(temperature, "temperature", "critical_c"),
                hysteresis_c=_require_real(temperature, "temperature", "hysteresis_c"),
            ),
            battery=BatteryAlarmPolicy(
                critical_v=_require_real(battery, "battery", "critical_v"),
                hysteresis_v=_require_real(battery, "battery", "hysteresis_v"),
            ),
            mode=ModeAlarmPolicy(
                alarm_on_safe=_require_bool(mode, "mode", "alarm_on_safe"),
            ),
            sequence=SequenceAlarmPolicy(
                detect_gaps=_require_bool(sequence, "sequence", "detect_gaps"),
            ),
        )
    except (TypeError, ValueError) as exc:
        raise AlarmPolicyValidationError(f"{source}: {exc}") from exc


def parse_alarm_policy(document: str, *, source: str = "<memory>") -> AlarmPolicy:
    """Parse and strictly validate one alarm-policy TOML document."""

    if not isinstance(document, str):
        raise TypeError("document must be a string")
    if not isinstance(source, str):
        raise TypeError("source must be a string")
    if not source:
        raise ValueError("source must not be empty")

    try:
        parsed: Mapping[str, object] = tomllib.loads(document)
    except tomllib.TOMLDecodeError as exc:
        raise AlarmPolicyParseError(f"{source}: invalid TOML: {exc}") from exc
    return _policy_from_mapping(parsed, source=source)

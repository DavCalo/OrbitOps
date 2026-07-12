"""Strict TOML parser for OrbitOps mission profiles."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping

from orbitops.link.config import LinkConfig

from .errors import MissionProfileParseError, MissionProfileValidationError
from .model import MissionProfile

_TOP_LEVEL_KEYS = frozenset({"schema_version", "name", "description", "link"})
_REQUIRED_TOP_LEVEL_KEYS = frozenset({"schema_version", "name", "link"})
_LINK_KEYS = frozenset(
    {
        "seed",
        "loss_rate",
        "duplicate_rate",
        "corrupt_rate",
        "latency_ms",
        "jitter_ms",
        "reorder_window",
    }
)


def _format_keys(keys: set[str] | frozenset[str]) -> str:
    return ", ".join(sorted(keys))


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


def _read_int(table: Mapping[str, object], key: str, default: int) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"link.{key} must be an integer")
    return value


def _read_rate(table: Mapping[str, object], key: str, default: float) -> float:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"link.{key} must be a real number")
    return float(value)


def _profile_from_mapping(
    document: Mapping[str, object],
    *,
    source: str,
) -> MissionProfile:
    unknown_top_level = set(document) - _TOP_LEVEL_KEYS
    if unknown_top_level:
        raise MissionProfileValidationError(
            f"{source}: unknown top-level key(s): {_format_keys(unknown_top_level)}"
        )

    missing = _REQUIRED_TOP_LEVEL_KEYS - set(document)
    if missing:
        raise MissionProfileValidationError(
            f"{source}: missing required key(s): {_format_keys(missing)}"
        )

    raw_link = document["link"]
    if not isinstance(raw_link, dict):
        raise MissionProfileValidationError(f"{source}: link must be a TOML table")
    link: Mapping[str, object] = raw_link

    unknown_link = set(link) - _LINK_KEYS
    if unknown_link:
        raise MissionProfileValidationError(
            f"{source}: unknown link key(s): {_format_keys(unknown_link)}"
        )

    try:
        schema_version = _read_int(document, "schema_version", 0)
        name = _require_string(document, "name")
        description = _read_optional_string(document, "description")
        link_config = LinkConfig(
            seed=_read_int(link, "seed", 0),
            loss_rate=_read_rate(link, "loss_rate", 0.0),
            duplicate_rate=_read_rate(link, "duplicate_rate", 0.0),
            corrupt_rate=_read_rate(link, "corrupt_rate", 0.0),
            latency_ms=_read_int(link, "latency_ms", 0),
            jitter_ms=_read_int(link, "jitter_ms", 0),
            reorder_window=_read_int(link, "reorder_window", 0),
        )
        return MissionProfile(
            schema_version=schema_version,
            name=name,
            description=description,
            link_config=link_config,
        )
    except (TypeError, ValueError) as exc:
        raise MissionProfileValidationError(f"{source}: {exc}") from exc


def parse_mission_profile(document: str, *, source: str = "<memory>") -> MissionProfile:
    """Parse and strictly validate one mission-profile TOML document."""

    if not isinstance(document, str):
        raise TypeError("document must be a string")
    if not isinstance(source, str):
        raise TypeError("source must be a string")
    if not source:
        raise ValueError("source must not be empty")

    try:
        parsed: Mapping[str, object] = tomllib.loads(document)
    except tomllib.TOMLDecodeError as exc:
        raise MissionProfileParseError(f"{source}: invalid TOML: {exc}") from exc

    return _profile_from_mapping(parsed, source=source)

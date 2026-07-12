"""Versioned, replayable JSONL events for the OrbitOps link emulator."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import TypeAlias

LINK_EVENT_SCHEMA_VERSION = 2
_SUPPORTED_LINK_EVENT_SCHEMA_VERSIONS = frozenset({1, LINK_EVENT_SCHEMA_VERSION})
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")

JsonScalar: TypeAlias = str | int | float | bool | None
EventAttributes: TypeAlias = Mapping[str, JsonScalar]


class LinkEventType(StrEnum):
    """Stable event names emitted by one link-emulator run."""

    RUN_METADATA = "run_metadata"
    PACKET_RECEIVED = "packet_received"
    PACKET_DROPPED = "packet_dropped"
    PACKET_DELAYED = "packet_delayed"
    PACKET_DUPLICATED = "packet_duplicated"
    PACKET_CORRUPTED = "packet_corrupted"
    DELIVERY_SCHEDULED = "delivery_scheduled"
    PACKET_REORDERED = "packet_reordered"
    PACKET_FORWARDED = "packet_forwarded"
    RUN_SUMMARY = "run_summary"


def _validate_non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _validate_optional_non_empty_string(name: str, value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string or None")
    if not value.strip():
        raise ValueError(f"{name} must be non-empty when provided")
    if "\x00" in value:
        raise ValueError(f"{name} must not contain NUL characters")
    return value


def _validate_attributes(attributes: object) -> dict[str, JsonScalar]:
    if not isinstance(attributes, Mapping):
        raise TypeError("attributes must be a mapping")

    validated: dict[str, JsonScalar] = {}
    for key, value in attributes.items():
        if not isinstance(key, str) or not key:
            raise ValueError("attribute names must be non-empty strings")
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise TypeError(f"attribute {key!r} has an unsupported value")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"attribute {key!r} must be finite")
        validated[key] = value
    return validated


@dataclass(frozen=True, slots=True)
class LinkRunMetadata:
    """Identity and effective-configuration evidence for one link run."""

    configuration_fingerprint: str
    profile_name: str | None = None
    profile_reference: str | None = None
    profile_schema_version: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.configuration_fingerprint, str):
            raise TypeError("configuration_fingerprint must be a string")
        if _FINGERPRINT_PATTERN.fullmatch(self.configuration_fingerprint) is None:
            raise ValueError(
                "configuration_fingerprint must use the form sha256:<64 lowercase hex digits>"
            )

        name = _validate_optional_non_empty_string("profile_name", self.profile_name)
        reference = _validate_optional_non_empty_string(
            "profile_reference",
            self.profile_reference,
        )
        schema_version = self.profile_schema_version
        identity_values = (name, reference, schema_version)
        populated = sum(value is not None for value in identity_values)
        if populated not in {0, 3}:
            raise ValueError(
                "profile_name, profile_reference, and profile_schema_version "
                "must be provided together"
            )
        if schema_version is not None:
            if isinstance(schema_version, bool) or not isinstance(schema_version, int):
                raise TypeError("profile_schema_version must be an integer or None")
            if schema_version <= 0:
                raise ValueError("profile_schema_version must be positive")

    def to_attributes(self) -> dict[str, JsonScalar]:
        """Return the stable scalar metadata representation."""

        return {
            "configuration_fingerprint": self.configuration_fingerprint,
            "profile_name": self.profile_name,
            "profile_reference": self.profile_reference,
            "profile_schema_version": self.profile_schema_version,
        }

    @classmethod
    def from_attributes(cls, attributes: object) -> LinkRunMetadata:
        """Validate and decode run metadata from event attributes."""

        validated = _validate_attributes(attributes)
        expected = {
            "configuration_fingerprint",
            "profile_name",
            "profile_reference",
            "profile_schema_version",
        }
        if set(validated) != expected:
            missing = sorted(expected - set(validated))
            extra = sorted(set(validated) - expected)
            raise ValueError(f"invalid run_metadata keys: missing={missing}, extra={extra}")

        fingerprint = validated["configuration_fingerprint"]
        if not isinstance(fingerprint, str):
            raise TypeError("configuration_fingerprint must be a string")
        profile_schema_version = validated["profile_schema_version"]
        if profile_schema_version is not None and (
            isinstance(profile_schema_version, bool) or not isinstance(profile_schema_version, int)
        ):
            raise TypeError("profile_schema_version must be an integer or None")

        return cls(
            configuration_fingerprint=fingerprint,
            profile_name=_validate_optional_non_empty_string(
                "profile_name",
                validated["profile_name"],
            ),
            profile_reference=_validate_optional_non_empty_string(
                "profile_reference",
                validated["profile_reference"],
            ),
            profile_schema_version=profile_schema_version,
        )


@dataclass(frozen=True, slots=True)
class LinkEvent:
    """One immutable, schema-versioned link-emulator event."""

    session_id: str
    event_index: int
    elapsed_ns: int
    event_type: LinkEventType
    packet_index: int | None = None
    attributes: EventAttributes = field(default_factory=dict)
    schema_version: int = LINK_EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        _validate_non_negative_int("event_index", self.event_index)
        _validate_non_negative_int("elapsed_ns", self.elapsed_ns)
        if not isinstance(self.event_type, LinkEventType):
            raise TypeError("event_type must be a LinkEventType")
        if self.packet_index is not None:
            _validate_non_negative_int("packet_index", self.packet_index)
        schema_version = _validate_non_negative_int("schema_version", self.schema_version)
        if schema_version not in _SUPPORTED_LINK_EVENT_SCHEMA_VERSIONS:
            raise ValueError(f"unsupported link event schema version {schema_version}")
        if self.event_type is LinkEventType.RUN_METADATA:
            if schema_version < 2:
                raise ValueError("run_metadata requires link event schema version 2")
            if self.packet_index is not None:
                raise ValueError("run_metadata packet_index must be null")
            attributes = LinkRunMetadata.from_attributes(self.attributes).to_attributes()
        else:
            attributes = _validate_attributes(self.attributes)
        if self.event_type is LinkEventType.RUN_SUMMARY and self.packet_index is not None:
            raise ValueError("run_summary packet_index must be null")
        object.__setattr__(self, "attributes", MappingProxyType(attributes))

    def to_dict(self) -> dict[str, object]:
        """Return the canonical JSON-compatible representation."""

        return {
            "attributes": dict(self.attributes),
            "elapsed_ns": self.elapsed_ns,
            "event_index": self.event_index,
            "event_type": self.event_type.value,
            "packet_index": self.packet_index,
            "schema_version": self.schema_version,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, payload: object) -> LinkEvent:
        """Validate and decode one JSON-compatible event object."""

        if not isinstance(payload, dict):
            raise ValueError("event record must be a JSON object")
        expected = {
            "attributes",
            "elapsed_ns",
            "event_index",
            "event_type",
            "packet_index",
            "schema_version",
            "session_id",
        }
        if set(payload) != expected:
            missing = sorted(expected - set(payload))
            extra = sorted(set(payload) - expected)
            raise ValueError(f"invalid event keys: missing={missing}, extra={extra}")

        session_id = payload["session_id"]
        if not isinstance(session_id, str):
            raise ValueError("session_id must be a string")
        event_type_value = payload["event_type"]
        if not isinstance(event_type_value, str):
            raise ValueError("event_type must be a string")
        packet_index_value = payload["packet_index"]
        if packet_index_value is not None:
            packet_index_value = _validate_non_negative_int(
                "packet_index",
                packet_index_value,
            )

        try:
            return cls(
                session_id=session_id,
                event_index=_validate_non_negative_int(
                    "event_index",
                    payload["event_index"],
                ),
                elapsed_ns=_validate_non_negative_int(
                    "elapsed_ns",
                    payload["elapsed_ns"],
                ),
                event_type=LinkEventType(event_type_value),
                packet_index=packet_index_value,
                attributes=_validate_attributes(payload["attributes"]),
                schema_version=_validate_non_negative_int(
                    "schema_version",
                    payload["schema_version"],
                ),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid link event: {exc}") from exc


EventSink: TypeAlias = Callable[[LinkEvent], None]


class JsonlEventRecorder:
    """Write a complete link-event stream as canonical line-delimited JSON."""

    __slots__ = ("_file", "path")

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("w", encoding="utf-8")

    def write(self, event: LinkEvent) -> None:
        if self._file.closed:
            raise RuntimeError("event recorder is closed")
        self._file.write(json.dumps(event.to_dict(), separators=(",", ":"), sort_keys=True) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> JsonlEventRecorder:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


def load_link_events(path: Path) -> tuple[LinkEvent, ...]:
    """Load and structurally validate a link-event JSONL file.

    Partial logs without a summary are accepted so interrupted runs remain
    inspectable. Version 1 logs remain readable. Version 2 streams must begin
    with exactly one ``run_metadata`` event.
    """

    events: list[LinkEvent] = []
    session_id: str | None = None
    schema_version: int | None = None
    previous_elapsed_ns = -1
    summary_seen = False
    metadata_seen = False

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                event = LinkEvent.from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid link event at line {line_number}") from exc

            if event.event_index != len(events):
                raise ValueError(f"non-contiguous event_index at line {line_number}")
            if session_id is None:
                session_id = event.session_id
            elif event.session_id != session_id:
                raise ValueError(f"session_id changed at line {line_number}")
            if schema_version is None:
                schema_version = event.schema_version
            elif event.schema_version != schema_version:
                raise ValueError(f"schema_version changed at line {line_number}")
            if event.elapsed_ns < previous_elapsed_ns:
                raise ValueError(f"elapsed_ns moved backwards at line {line_number}")
            if summary_seen:
                raise ValueError("run_summary must be the final event")

            if event.schema_version >= 2:
                if not events and event.event_type is not LinkEventType.RUN_METADATA:
                    raise ValueError("schema version 2 streams must begin with run_metadata")
                if event.event_type is LinkEventType.RUN_METADATA:
                    if metadata_seen or events:
                        raise ValueError("run_metadata may appear only once as the first event")
                    metadata_seen = True

            if event.event_type is LinkEventType.RUN_SUMMARY:
                summary_seen = True

            events.append(event)
            previous_elapsed_ns = event.elapsed_ns

    return tuple(events)

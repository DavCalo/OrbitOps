"""Versioned, auditable JSONL events for OrbitOps alarm lifecycles."""

from __future__ import annotations

import json
import math
import re
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import TypeAlias

from .alarm_policies import AlarmPolicy, alarm_policy_fingerprint
from .alarms import AlarmSeverity, AlarmTransition, AlarmTransitionType

ALARM_EVENT_SCHEMA_VERSION = 1
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_MAX_PACKET_SEQUENCE = 0xFFFFFFFF

JsonScalar: TypeAlias = str | int | float | bool | None
AlarmEventAttributes: TypeAlias = Mapping[str, JsonScalar]
ClockNs: TypeAlias = Callable[[], int]


class AlarmEventType(StrEnum):
    """Stable record types emitted by one alarm-observation run."""

    RUN_METADATA = "run_metadata"
    ALARM_RAISED = "alarm_raised"
    ALARM_UPDATED = "alarm_updated"
    ALARM_CLEARED = "alarm_cleared"
    RUN_SUMMARY = "run_summary"


_TRANSITION_EVENT_TYPES = frozenset(
    {
        AlarmEventType.ALARM_RAISED,
        AlarmEventType.ALARM_UPDATED,
        AlarmEventType.ALARM_CLEARED,
    }
)
_EVENT_TYPE_BY_TRANSITION = {
    AlarmTransitionType.RAISED: AlarmEventType.ALARM_RAISED,
    AlarmTransitionType.UPDATED: AlarmEventType.ALARM_UPDATED,
    AlarmTransitionType.CLEARED: AlarmEventType.ALARM_CLEARED,
}


def _validate_non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _validate_non_empty_string(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")
    if "\x00" in value:
        raise ValueError(f"{name} must not contain NUL characters")
    return value


def _validate_json_scalar(
    name: str,
    value: object,
    *,
    allow_bool: bool = False,
) -> JsonScalar:
    if isinstance(value, bool):
        if allow_bool:
            return value
        raise TypeError(f"{name} must not be a boolean")
    if not isinstance(value, (str, int, float, type(None))):
        raise TypeError(f"{name} has an unsupported value")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _validate_attributes(attributes: object) -> dict[str, JsonScalar]:
    if not isinstance(attributes, Mapping):
        raise TypeError("attributes must be a mapping")

    validated: dict[str, JsonScalar] = {}
    for key, value in attributes.items():
        if not isinstance(key, str) or not key:
            raise ValueError("attribute names must be non-empty strings")
        validated[key] = _validate_json_scalar(
            f"attribute {key!r}",
            value,
            allow_bool=True,
        )
    return validated


@dataclass(frozen=True, slots=True)
class AlarmRunMetadata:
    """Policy identity and reproducibility evidence for one alarm run."""

    policy_name: str
    policy_reference: str
    policy_schema_version: int
    policy_fingerprint: str

    def __post_init__(self) -> None:
        _validate_non_empty_string("policy_name", self.policy_name)
        _validate_non_empty_string("policy_reference", self.policy_reference)
        schema_version = _validate_non_negative_int(
            "policy_schema_version",
            self.policy_schema_version,
        )
        if schema_version <= 0:
            raise ValueError("policy_schema_version must be positive")
        if not isinstance(self.policy_fingerprint, str):
            raise TypeError("policy_fingerprint must be a string")
        if _FINGERPRINT_PATTERN.fullmatch(self.policy_fingerprint) is None:
            raise ValueError("policy_fingerprint must use sha256:<64 lowercase hex digits>")

    @classmethod
    def from_policy(
        cls,
        policy: AlarmPolicy,
        *,
        reference: str,
    ) -> AlarmRunMetadata:
        """Build metadata for one validated effective policy."""

        if not isinstance(policy, AlarmPolicy):
            raise TypeError("policy must be an AlarmPolicy instance")
        return cls(
            policy_name=policy.name,
            policy_reference=reference,
            policy_schema_version=policy.schema_version,
            policy_fingerprint=alarm_policy_fingerprint(policy),
        )

    def to_attributes(self) -> dict[str, JsonScalar]:
        """Return the stable scalar metadata representation."""

        return {
            "policy_fingerprint": self.policy_fingerprint,
            "policy_name": self.policy_name,
            "policy_reference": self.policy_reference,
            "policy_schema_version": self.policy_schema_version,
        }

    @classmethod
    def from_attributes(cls, attributes: object) -> AlarmRunMetadata:
        """Validate and decode metadata from event attributes."""

        validated = _validate_attributes(attributes)
        expected = {
            "policy_fingerprint",
            "policy_name",
            "policy_reference",
            "policy_schema_version",
        }
        if set(validated) != expected:
            missing = sorted(expected - set(validated))
            extra = sorted(set(validated) - expected)
            raise ValueError(f"invalid run_metadata keys: missing={missing}, extra={extra}")

        name = _validate_non_empty_string("policy_name", validated["policy_name"])
        reference = _validate_non_empty_string(
            "policy_reference",
            validated["policy_reference"],
        )
        fingerprint = _validate_non_empty_string(
            "policy_fingerprint",
            validated["policy_fingerprint"],
        )
        schema_version = _validate_non_negative_int(
            "policy_schema_version",
            validated["policy_schema_version"],
        )
        return cls(
            policy_name=name,
            policy_reference=reference,
            policy_schema_version=schema_version,
            policy_fingerprint=fingerprint,
        )


@dataclass(frozen=True, slots=True)
class AlarmRunStatistics:
    """Independently recomputable alarm-transition counters."""

    transitions_raised: int = 0
    transitions_updated: int = 0
    transitions_cleared: int = 0

    def __post_init__(self) -> None:
        _validate_non_negative_int("transitions_raised", self.transitions_raised)
        _validate_non_negative_int("transitions_updated", self.transitions_updated)
        _validate_non_negative_int("transitions_cleared", self.transitions_cleared)

    @property
    def transitions_total(self) -> int:
        """Return the total number of lifecycle transitions."""

        return self.transitions_raised + self.transitions_updated + self.transitions_cleared

    def with_transition(self, transition: AlarmTransitionType) -> AlarmRunStatistics:
        """Return counters incremented for one typed lifecycle transition."""

        if transition is AlarmTransitionType.RAISED:
            return AlarmRunStatistics(
                transitions_raised=self.transitions_raised + 1,
                transitions_updated=self.transitions_updated,
                transitions_cleared=self.transitions_cleared,
            )
        if transition is AlarmTransitionType.UPDATED:
            return AlarmRunStatistics(
                transitions_raised=self.transitions_raised,
                transitions_updated=self.transitions_updated + 1,
                transitions_cleared=self.transitions_cleared,
            )
        return AlarmRunStatistics(
            transitions_raised=self.transitions_raised,
            transitions_updated=self.transitions_updated,
            transitions_cleared=self.transitions_cleared + 1,
        )

    def to_attributes(self) -> dict[str, JsonScalar]:
        """Return the stable run-summary representation."""

        return {
            "transitions_cleared": self.transitions_cleared,
            "transitions_raised": self.transitions_raised,
            "transitions_total": self.transitions_total,
            "transitions_updated": self.transitions_updated,
        }

    @classmethod
    def from_attributes(cls, attributes: object) -> AlarmRunStatistics:
        """Validate and decode counters from summary attributes."""

        validated = _validate_attributes(attributes)
        expected = {
            "transitions_cleared",
            "transitions_raised",
            "transitions_total",
            "transitions_updated",
        }
        if set(validated) != expected:
            missing = sorted(expected - set(validated))
            extra = sorted(set(validated) - expected)
            raise ValueError(f"invalid run_summary keys: missing={missing}, extra={extra}")

        statistics = cls(
            transitions_raised=_validate_non_negative_int(
                "transitions_raised",
                validated["transitions_raised"],
            ),
            transitions_updated=_validate_non_negative_int(
                "transitions_updated",
                validated["transitions_updated"],
            ),
            transitions_cleared=_validate_non_negative_int(
                "transitions_cleared",
                validated["transitions_cleared"],
            ),
        )
        total = _validate_non_negative_int(
            "transitions_total",
            validated["transitions_total"],
        )
        if total != statistics.transitions_total:
            raise ValueError("transitions_total does not match raised + updated + cleared")
        return statistics


@dataclass(frozen=True, slots=True)
class AlarmEvent:
    """One immutable, schema-versioned alarm event."""

    session_id: str
    event_index: int
    elapsed_ns: int
    event_type: AlarmEventType
    packet_sequence: int | None = None
    attributes: AlarmEventAttributes = field(default_factory=dict)
    schema_version: int = ALARM_EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_non_empty_string("session_id", self.session_id)
        _validate_non_negative_int("event_index", self.event_index)
        _validate_non_negative_int("elapsed_ns", self.elapsed_ns)
        if not isinstance(self.event_type, AlarmEventType):
            raise TypeError("event_type must be an AlarmEventType")
        schema_version = _validate_non_negative_int(
            "schema_version",
            self.schema_version,
        )
        if schema_version != ALARM_EVENT_SCHEMA_VERSION:
            raise ValueError(f"unsupported alarm event schema version {schema_version}")

        if self.event_type in _TRANSITION_EVENT_TYPES:
            if self.packet_sequence is None:
                raise ValueError("alarm transition packet_sequence must be provided")
            packet_sequence = _validate_non_negative_int(
                "packet_sequence",
                self.packet_sequence,
            )
            if packet_sequence > _MAX_PACKET_SEQUENCE:
                raise ValueError("packet_sequence must fit an unsigned 32-bit integer")
            attributes = self._validate_transition_attributes(self.attributes)
        elif self.event_type is AlarmEventType.RUN_METADATA:
            if self.packet_sequence is not None:
                raise ValueError("run_metadata packet_sequence must be null")
            attributes = AlarmRunMetadata.from_attributes(self.attributes).to_attributes()
        else:
            if self.packet_sequence is not None:
                raise ValueError("run_summary packet_sequence must be null")
            attributes = AlarmRunStatistics.from_attributes(self.attributes).to_attributes()
        object.__setattr__(self, "attributes", MappingProxyType(attributes))

    @staticmethod
    def _validate_transition_attributes(
        attributes: object,
    ) -> dict[str, JsonScalar]:
        validated = _validate_attributes(attributes)
        expected = {
            "alarm_identity",
            "code",
            "message",
            "observed_value",
            "severity",
            "threshold",
        }
        if set(validated) != expected:
            missing = sorted(expected - set(validated))
            extra = sorted(set(validated) - expected)
            raise ValueError(f"invalid alarm transition keys: missing={missing}, extra={extra}")

        identity = _validate_non_empty_string(
            "alarm_identity",
            validated["alarm_identity"],
        )
        code = _validate_non_empty_string("code", validated["code"])
        message = _validate_non_empty_string("message", validated["message"])
        severity_value = _validate_non_empty_string(
            "severity",
            validated["severity"],
        )
        try:
            severity = AlarmSeverity(severity_value)
        except ValueError as exc:
            raise ValueError(f"unsupported alarm severity {severity_value!r}") from exc
        observed = _validate_json_scalar(
            "observed_value",
            validated["observed_value"],
        )
        threshold = _validate_json_scalar("threshold", validated["threshold"])
        if isinstance(threshold, str):
            raise TypeError("threshold must be numeric or null")

        return {
            "alarm_identity": identity,
            "code": code,
            "message": message,
            "observed_value": observed,
            "severity": severity.value,
            "threshold": threshold,
        }

    @classmethod
    def from_transition(
        cls,
        *,
        session_id: str,
        event_index: int,
        elapsed_ns: int,
        packet_sequence: int,
        transition: AlarmTransition,
    ) -> AlarmEvent:
        """Encode one typed engine transition as a canonical event."""

        if not isinstance(transition, AlarmTransition):
            raise TypeError("transition must be an AlarmTransition")
        return cls(
            session_id=session_id,
            event_index=event_index,
            elapsed_ns=elapsed_ns,
            event_type=_EVENT_TYPE_BY_TRANSITION[transition.transition],
            packet_sequence=packet_sequence,
            attributes={
                "alarm_identity": transition.identity.name,
                "code": transition.code,
                "message": transition.message,
                "observed_value": transition.observed_value,
                "severity": transition.severity.value,
                "threshold": transition.threshold,
            },
        )

    def to_dict(self) -> dict[str, object]:
        """Return the canonical JSON-compatible representation."""

        return {
            "attributes": dict(self.attributes),
            "elapsed_ns": self.elapsed_ns,
            "event_index": self.event_index,
            "event_type": self.event_type.value,
            "packet_sequence": self.packet_sequence,
            "schema_version": self.schema_version,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, payload: object) -> AlarmEvent:
        """Validate and decode one JSON-compatible event object."""

        if not isinstance(payload, dict):
            raise ValueError("alarm event record must be a JSON object")
        expected = {
            "attributes",
            "elapsed_ns",
            "event_index",
            "event_type",
            "packet_sequence",
            "schema_version",
            "session_id",
        }
        if set(payload) != expected:
            missing = sorted(expected - set(payload))
            extra = sorted(set(payload) - expected)
            raise ValueError(f"invalid alarm event keys: missing={missing}, extra={extra}")

        event_type = payload["event_type"]
        if not isinstance(event_type, str):
            raise ValueError("event_type must be a string")
        session_id = payload["session_id"]
        if not isinstance(session_id, str):
            raise ValueError("session_id must be a string")
        packet_sequence = payload["packet_sequence"]
        if packet_sequence is not None:
            packet_sequence = _validate_non_negative_int(
                "packet_sequence",
                packet_sequence,
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
                event_type=AlarmEventType(event_type),
                packet_sequence=packet_sequence,
                attributes=_validate_attributes(payload["attributes"]),
                schema_version=_validate_non_negative_int(
                    "schema_version",
                    payload["schema_version"],
                ),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid alarm event: {exc}") from exc


class AlarmEventRecorder:
    """Write one complete alarm-event stream with metadata and summary."""

    __slots__ = (
        "_clock_ns",
        "_closed",
        "_event_index",
        "_file",
        "_start_ns",
        "_statistics",
        "path",
        "session_id",
    )

    def __init__(
        self,
        path: Path,
        metadata: AlarmRunMetadata,
        *,
        session_id: str | None = None,
        clock_ns: ClockNs = time.monotonic_ns,
    ) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be a pathlib.Path")
        if not isinstance(metadata, AlarmRunMetadata):
            raise TypeError("metadata must be an AlarmRunMetadata")
        if not callable(clock_ns):
            raise TypeError("clock_ns must be callable")

        self.path = path
        self.session_id = f"alarm-{uuid.uuid4().hex}" if session_id is None else session_id
        _validate_non_empty_string("session_id", self.session_id)
        self._clock_ns = clock_ns
        self._start_ns = _validate_non_negative_int("clock_ns", self._clock_ns())
        self._event_index = 0
        self._statistics = AlarmRunStatistics()
        self._closed = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", encoding="utf-8")
        self._write_event(
            AlarmEvent(
                session_id=self.session_id,
                event_index=0,
                elapsed_ns=0,
                event_type=AlarmEventType.RUN_METADATA,
                attributes=metadata.to_attributes(),
            )
        )

    @property
    def statistics(self) -> AlarmRunStatistics:
        """Return counters accumulated so far."""

        return self._statistics

    def _elapsed_ns(self) -> int:
        now_ns = _validate_non_negative_int("clock_ns", self._clock_ns())
        return max(0, now_ns - self._start_ns)

    def _write_event(self, event: AlarmEvent) -> None:
        if self._closed:
            raise RuntimeError("alarm event recorder is closed")
        self._file.write(
            json.dumps(
                event.to_dict(),
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )
        self._file.flush()
        self._event_index += 1

    def write_transitions(
        self,
        packet_sequence: int,
        transitions: Sequence[AlarmTransition],
    ) -> None:
        """Write transitions emitted while processing one telemetry packet."""

        for transition in transitions:
            event = AlarmEvent.from_transition(
                session_id=self.session_id,
                event_index=self._event_index,
                elapsed_ns=self._elapsed_ns(),
                packet_sequence=packet_sequence,
                transition=transition,
            )
            self._write_event(event)
            self._statistics = self._statistics.with_transition(transition.transition)

    def close(self) -> None:
        """Write a final summary and close the underlying file exactly once."""

        if self._closed:
            return
        self._write_event(
            AlarmEvent(
                session_id=self.session_id,
                event_index=self._event_index,
                elapsed_ns=self._elapsed_ns(),
                event_type=AlarmEventType.RUN_SUMMARY,
                attributes=self._statistics.to_attributes(),
            )
        )
        self._file.close()
        self._closed = True

    def __enter__(self) -> AlarmEventRecorder:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


def statistics_from_events(
    events: Sequence[AlarmEvent],
) -> AlarmRunStatistics:
    """Recompute transition counters without trusting a summary record."""

    raised = sum(event.event_type is AlarmEventType.ALARM_RAISED for event in events)
    updated = sum(event.event_type is AlarmEventType.ALARM_UPDATED for event in events)
    cleared = sum(event.event_type is AlarmEventType.ALARM_CLEARED for event in events)
    return AlarmRunStatistics(raised, updated, cleared)


def run_metadata_from_events(
    events: Sequence[AlarmEvent],
) -> AlarmRunMetadata | None:
    """Return leading run metadata when present."""

    if not events or events[0].event_type is not AlarmEventType.RUN_METADATA:
        return None
    return AlarmRunMetadata.from_attributes(events[0].attributes)


def validate_run_summary(
    events: Sequence[AlarmEvent],
) -> AlarmRunStatistics:
    """Validate the final summary against independently recomputed counters."""

    if not events or events[-1].event_type is not AlarmEventType.RUN_SUMMARY:
        raise ValueError("alarm event stream does not contain a final run_summary")
    recorded = AlarmRunStatistics.from_attributes(events[-1].attributes)
    recomputed = statistics_from_events(events[:-1])
    if recorded != recomputed:
        raise ValueError(
            "alarm run_summary counters do not match events: "
            f"recorded={recorded}, recomputed={recomputed}"
        )
    return recorded


def load_alarm_events(path: Path) -> tuple[AlarmEvent, ...]:
    """Load and validate one complete or interrupted alarm-event stream."""

    events: list[AlarmEvent] = []
    session_id: str | None = None
    previous_elapsed_ns = -1
    summary_seen = False

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                event = AlarmEvent.from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid alarm event at line {line_number}") from exc

            if event.event_index != len(events):
                raise ValueError(f"non-contiguous event_index at line {line_number}")
            if session_id is None:
                session_id = event.session_id
            elif event.session_id != session_id:
                raise ValueError(f"session_id changed at line {line_number}")
            if event.elapsed_ns < previous_elapsed_ns:
                raise ValueError(f"elapsed_ns moved backwards at line {line_number}")
            if summary_seen:
                raise ValueError("run_summary must be the final event")
            if not events and event.event_type is not AlarmEventType.RUN_METADATA:
                raise ValueError("alarm event streams must begin with run_metadata")
            if events and event.event_type is AlarmEventType.RUN_METADATA:
                raise ValueError("run_metadata may appear only once as the first event")
            if event.event_type is AlarmEventType.RUN_SUMMARY:
                summary_seen = True

            events.append(event)
            previous_elapsed_ns = event.elapsed_ns

    if events and events[-1].event_type is AlarmEventType.RUN_SUMMARY:
        validate_run_summary(events)
    return tuple(events)

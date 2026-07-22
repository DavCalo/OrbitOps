"""Immutable normalized models for unified OrbitOps session inspection."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TypeAlias

from .correlation import (
    CONTRACT_SEMANTICS,
    LANE_PRECEDENCE,
    CorrelationDecision,
    CorrelationKind,
    EvidenceLane,
    SourceCompleteness,
    classify_source_completeness,
    presentation_key,
)
from .errors import IncompatibleEvidenceError, IncompleteEvidenceError

JsonScalar: TypeAlias = str | int | float | bool | None
ImmutableAttributes: TypeAlias = Mapping[str, JsonScalar]

_MAX_PACKET_SEQUENCE = 0xFFFFFFFF
_LANE_RANK = {lane: rank for rank, lane in enumerate(LANE_PRECEDENCE)}
_SEVERITY_RANK: Mapping[DiagnosticSeverity, int]


class TimelineEntryKind(StrEnum):
    """Stable categories stored in the normalized operational timeline."""

    TELEMETRY_PACKET = "telemetry_packet"
    TELEMETRY_REJECTED = "telemetry_rejected"
    ALARM_TRANSITION = "alarm_transition"
    LINK_EVENT = "link_event"


class DiagnosticSeverity(StrEnum):
    """Stable diagnostic severity used by the inspection core."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


_SEVERITY_RANK = MappingProxyType(
    {
        DiagnosticSeverity.ERROR: 0,
        DiagnosticSeverity.WARNING: 1,
        DiagnosticSeverity.INFO: 2,
    }
)


class DiagnosticCode(StrEnum):
    """Stable machine-readable diagnostic identifiers."""

    SOURCE_EMPTY = "source_empty"
    SOURCE_NOT_PROVIDED = "source_not_provided"
    SOURCE_INCOMPLETE = "source_incomplete"
    SOURCE_SUMMARY_MISSING = "source_summary_missing"
    TELEMETRY_PACKET_REJECTED = "telemetry_packet_rejected"
    TELEMETRY_SEQUENCE_GAP = "telemetry_sequence_gap"
    TELEMETRY_SEQUENCE_DUPLICATE = "telemetry_sequence_duplicate"
    ALARM_CORRELATION_AMBIGUOUS = "alarm_correlation_ambiguous"
    ALARM_CORRELATION_IMPOSSIBLE = "alarm_correlation_impossible"
    LINK_CORRUPTION_OBSERVED = "link_corruption_observed"
    METADATA_MISMATCH = "metadata_mismatch"


def _validate_non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _validate_optional_non_negative_int(name: str, value: object) -> int | None:
    if value is None:
        return None
    return _validate_non_negative_int(name, value)


def _validate_non_empty_string(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")
    if "\x00" in value:
        raise ValueError(f"{name} must not contain NUL characters")
    return value


def _freeze_attributes(attributes: object) -> ImmutableAttributes:
    if not isinstance(attributes, Mapping):
        raise TypeError("attributes must be a mapping")
    frozen: dict[str, JsonScalar] = {}
    for key, value in attributes.items():
        if not isinstance(key, str) or not key:
            raise ValueError("attribute names must be non-empty strings")
        if not isinstance(value, str | int | float | bool | None):
            raise TypeError(f"attribute {key!r} has an unsupported value")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"attribute {key!r} must be finite")
        frozen[key] = value
    return MappingProxyType(frozen)


def _freeze_counters(counters: object) -> Mapping[str, int]:
    if not isinstance(counters, Mapping):
        raise TypeError("counters must be a mapping")
    frozen: dict[str, int] = {}
    for key, value in counters.items():
        if not isinstance(key, str) or not key:
            raise ValueError("counter names must be non-empty strings")
        frozen[key] = _validate_non_negative_int(f"counter {key!r}", value)
    return MappingProxyType(frozen)


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    """Source-local identity and completion context for one evidence lane."""

    lane: EvidenceLane
    source_name: str
    record_count: int
    completeness: SourceCompleteness
    schema_version: int | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.lane, EvidenceLane):
            raise TypeError("lane must be an EvidenceLane")
        _validate_non_empty_string("source_name", self.source_name)
        _validate_non_negative_int("record_count", self.record_count)
        if not isinstance(self.completeness, SourceCompleteness):
            raise TypeError("completeness must be a SourceCompleteness")
        if self.schema_version is not None:
            schema_version = _validate_non_negative_int("schema_version", self.schema_version)
            if schema_version <= 0:
                raise ValueError("schema_version must be positive")
            if schema_version not in CONTRACT_SEMANTICS[self.lane].readable_schema_versions:
                raise ValueError(f"unsupported {self.lane.value} schema version {schema_version}")
        if self.session_id is not None:
            _validate_non_empty_string("session_id", self.session_id)
        if self.lane is EvidenceLane.TELEMETRY and self.session_id is not None:
            raise ValueError("telemetry recording schema has no session_id")


@dataclass(frozen=True, slots=True)
class LaneSummary:
    """Independently derived counters and metadata for one validated lane."""

    source: SourceDescriptor
    summary_present: bool
    counters: Mapping[str, int] = field(default_factory=dict)
    metadata: ImmutableAttributes = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.source, SourceDescriptor):
            raise TypeError("source must be a SourceDescriptor")
        if not isinstance(self.summary_present, bool):
            raise TypeError("summary_present must be a boolean")
        expected = classify_source_completeness(
            self.source.lane,
            self.source.record_count,
            summary_present=self.summary_present,
        )
        if self.source.completeness is not expected:
            raise ValueError(
                "source completeness does not match lane record count and summary presence"
            )
        object.__setattr__(self, "counters", _freeze_counters(self.counters))
        object.__setattr__(self, "metadata", _freeze_attributes(self.metadata))


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    """One normalized operational entry preserving lane and source position."""

    lane: EvidenceLane
    source_index: int
    kind: TimelineEntryKind
    event_type: str
    received_at: float | None = None
    elapsed_ns: int | None = None
    packet_sequence: int | None = None
    packet_index: int | None = None
    telemetry_timestamp_ms: int | None = None
    attributes: ImmutableAttributes = field(default_factory=dict)
    correlation: CorrelationDecision | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.lane, EvidenceLane):
            raise TypeError("lane must be an EvidenceLane")
        _validate_non_negative_int("source_index", self.source_index)
        if not isinstance(self.kind, TimelineEntryKind):
            raise TypeError("kind must be a TimelineEntryKind")
        _validate_non_empty_string("event_type", self.event_type)

        if self.received_at is not None:
            if isinstance(self.received_at, bool) or not isinstance(self.received_at, int | float):
                raise TypeError("received_at must be a real number or None")
            received_at = float(self.received_at)
            if not math.isfinite(received_at) or received_at < 0.0:
                raise ValueError("received_at must be finite and non-negative")
            object.__setattr__(self, "received_at", received_at)

        elapsed_ns = _validate_optional_non_negative_int("elapsed_ns", self.elapsed_ns)
        packet_sequence = _validate_optional_non_negative_int(
            "packet_sequence", self.packet_sequence
        )
        if packet_sequence is not None and packet_sequence > _MAX_PACKET_SEQUENCE:
            raise ValueError("packet_sequence must fit an unsigned 32-bit integer")
        _validate_optional_non_negative_int("packet_index", self.packet_index)
        telemetry_timestamp_ms = _validate_optional_non_negative_int(
            "telemetry_timestamp_ms", self.telemetry_timestamp_ms
        )
        if telemetry_timestamp_ms is not None and telemetry_timestamp_ms > 0xFFFFFFFFFFFFFFFF:
            raise ValueError("telemetry_timestamp_ms must fit an unsigned 64-bit integer")
        if self.correlation is not None and not isinstance(self.correlation, CorrelationDecision):
            raise TypeError("correlation must be a CorrelationDecision or None")

        self._validate_lane_shape(elapsed_ns, packet_sequence)
        object.__setattr__(self, "attributes", _freeze_attributes(self.attributes))

    def _validate_lane_shape(self, elapsed_ns: int | None, packet_sequence: int | None) -> None:
        if self.lane is EvidenceLane.TELEMETRY:
            if self.kind not in {
                TimelineEntryKind.TELEMETRY_PACKET,
                TimelineEntryKind.TELEMETRY_REJECTED,
            }:
                raise ValueError("telemetry lane requires a telemetry entry kind")
            if self.received_at is None:
                raise ValueError("telemetry entries require received_at")
            if elapsed_ns is not None or self.packet_index is not None:
                raise ValueError("telemetry entries cannot use elapsed_ns or packet_index")
            if self.correlation is not None:
                raise ValueError("telemetry entries do not carry correlation decisions")
            if self.kind is TimelineEntryKind.TELEMETRY_PACKET:
                if packet_sequence is None or self.telemetry_timestamp_ms is None:
                    raise ValueError(
                        "decoded telemetry entries require packet_sequence "
                        "and telemetry_timestamp_ms"
                    )
            elif packet_sequence is not None or self.telemetry_timestamp_ms is not None:
                raise ValueError("rejected telemetry entries cannot claim decoded packet fields")
            return

        if self.lane is EvidenceLane.ALARM:
            if self.kind is not TimelineEntryKind.ALARM_TRANSITION:
                raise ValueError("alarm lane requires alarm_transition entries")
            if self.received_at is not None or elapsed_ns is None:
                raise ValueError("alarm entries require elapsed_ns and cannot use received_at")
            if packet_sequence is None or self.packet_index is not None:
                raise ValueError(
                    "alarm entries require packet_sequence and cannot use packet_index"
                )
            if self.telemetry_timestamp_ms is not None:
                raise ValueError("alarm entries cannot use telemetry_timestamp_ms")
            if self.correlation is None:
                raise ValueError("alarm entries require an explicit correlation decision")
            if self.correlation.kind not in {
                CorrelationKind.EXACT,
                CorrelationKind.AMBIGUOUS,
                CorrelationKind.IMPOSSIBLE,
            }:
                raise ValueError("alarm correlation kind is not permitted by ADR 0005")
            return

        if self.kind is not TimelineEntryKind.LINK_EVENT:
            raise ValueError("link lane requires link_event entries")
        if self.received_at is not None or elapsed_ns is None:
            raise ValueError("link entries require elapsed_ns and cannot use received_at")
        if packet_sequence is not None or self.telemetry_timestamp_ms is not None:
            raise ValueError("link entries cannot claim telemetry packet fields")
        if self.correlation is not None:
            raise ValueError("link entries remain a separate lane without correlation decisions")

    @property
    def sort_key(self) -> tuple[int, int]:
        """Return deterministic presentation order without implying shared time."""

        return presentation_key(self.lane, self.source_index)


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One deterministic operator-facing diagnostic."""

    code: DiagnosticCode
    severity: DiagnosticSeverity
    message: str
    lane: EvidenceLane | None = None
    source_index: int | None = None
    related_lane: EvidenceLane | None = None
    related_source_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.code, DiagnosticCode):
            raise TypeError("code must be a DiagnosticCode")
        if not isinstance(self.severity, DiagnosticSeverity):
            raise TypeError("severity must be a DiagnosticSeverity")
        _validate_non_empty_string("message", self.message)
        if self.lane is not None and not isinstance(self.lane, EvidenceLane):
            raise TypeError("lane must be an EvidenceLane or None")
        if self.source_index is not None:
            _validate_non_negative_int("source_index", self.source_index)
            if self.lane is None:
                raise ValueError("source_index requires a lane")
        if self.related_lane is not None and not isinstance(self.related_lane, EvidenceLane):
            raise TypeError("related_lane must be an EvidenceLane or None")
        for index in self.related_source_indices:
            _validate_non_negative_int("related_source_indices item", index)
        if tuple(sorted(set(self.related_source_indices))) != self.related_source_indices:
            raise ValueError("related_source_indices must be unique and sorted")
        if self.related_source_indices and self.related_lane is None:
            if self.lane is None:
                raise ValueError("related_source_indices require related_lane when lane is absent")
            object.__setattr__(self, "related_lane", self.lane)
        if self.related_lane is not None and not self.related_source_indices:
            raise ValueError("related_lane requires related_source_indices")

    @property
    def sort_key(self) -> tuple[int, int, int, str, int, tuple[int, ...], str]:
        """Return deterministic diagnostic order."""

        lane_rank = len(LANE_PRECEDENCE) if self.lane is None else _LANE_RANK[self.lane]
        source_rank = -1 if self.source_index is None else self.source_index
        related_lane_rank = (
            len(LANE_PRECEDENCE) if self.related_lane is None else _LANE_RANK[self.related_lane]
        )
        return (
            lane_rank,
            source_rank,
            _SEVERITY_RANK[self.severity],
            self.code.value,
            related_lane_rank,
            self.related_source_indices,
            self.message,
        )


@dataclass(frozen=True, slots=True)
class NormalizedSession:
    """Complete immutable inspection model for the three evidence lanes."""

    sources: tuple[LaneSummary, ...]
    timeline: tuple[TimelineEntry, ...]
    diagnostics: tuple[Diagnostic, ...]

    def __post_init__(self) -> None:
        if any(not isinstance(summary, LaneSummary) for summary in self.sources):
            raise TypeError("sources must contain LaneSummary values")
        if any(not isinstance(entry, TimelineEntry) for entry in self.timeline):
            raise TypeError("timeline must contain TimelineEntry values")
        if any(not isinstance(item, Diagnostic) for item in self.diagnostics):
            raise TypeError("diagnostics must contain Diagnostic values")
        expected_lanes = tuple(LANE_PRECEDENCE)
        actual_lanes = tuple(summary.source.lane for summary in self.sources)
        if actual_lanes != expected_lanes:
            raise ValueError(
                "sources must contain telemetry, alarm, and link exactly once in order"
            )
        if tuple(sorted(self.timeline, key=lambda entry: entry.sort_key)) != self.timeline:
            raise ValueError("timeline entries must use deterministic presentation order")
        if tuple(sorted(self.diagnostics, key=lambda item: item.sort_key)) != self.diagnostics:
            raise ValueError("diagnostics must use deterministic order")
        available_lanes = set(actual_lanes)
        if any(entry.lane not in available_lanes for entry in self.timeline):
            raise ValueError("timeline entry references an unavailable lane")
        if any(
            diagnostic.lane is not None and diagnostic.lane not in available_lanes
            for diagnostic in self.diagnostics
        ):
            raise ValueError("diagnostic references an unavailable lane")
        if any(
            diagnostic.related_lane is not None and diagnostic.related_lane not in available_lanes
            for diagnostic in self.diagnostics
        ):
            raise ValueError("diagnostic related_lane references an unavailable lane")

    @property
    def has_incomplete_sources(self) -> bool:
        return any(
            summary.source.completeness is SourceCompleteness.INCOMPLETE for summary in self.sources
        )

    @property
    def has_incompatibilities(self) -> bool:
        return any(
            diagnostic.severity is DiagnosticSeverity.ERROR for diagnostic in self.diagnostics
        )

    @property
    def is_complete(self) -> bool:
        """Return whether no source is explicitly incomplete."""

        return not self.has_incomplete_sources

    @property
    def is_compatible(self) -> bool:
        """Return whether no deterministic error diagnostic is present."""

        return not self.has_incompatibilities

    def require_complete(self) -> None:
        """Raise when a caller requires every source to avoid incomplete state."""

        if self.has_incomplete_sources:
            raise IncompleteEvidenceError("session contains one or more incomplete sources")

    def require_compatible(self) -> None:
        """Raise when a caller requires all selected evidence to be unambiguous."""

        if self.has_incompatibilities:
            raise IncompatibleEvidenceError("session contains incompatible or ambiguous evidence")

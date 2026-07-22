"""Deterministic text and JSON report contracts for normalized sessions."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TypeAlias, TypedDict

from .correlation import CorrelationDecision, EvidenceLane, SourceCompleteness
from .models import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticSeverity,
    LaneSummary,
    NormalizedSession,
    TimelineEntry,
)

REPORT_FORMAT = "orbitops.session_report"
REPORT_FORMAT_VERSION = 1
EVIDENCE_BUNDLE_KIND = "operator_selected"
MAX_REPORT_EVENTS = 10_000
ALARM_SEVERITY_CHOICES = ("warning", "critical")
_MAX_PACKET_SEQUENCE = 0xFFFFFFFF

JsonScalar: TypeAlias = str | int | float | bool | None
ImmutableFilters: TypeAlias = Mapping[str, JsonScalar]


class _ReportMetadataDocument(TypedDict):
    cross_stream_provenance_verified: bool
    evidence_bundle: str
    report_format: str
    report_format_version: int


class _ReportSelectionDocument(TypedDict):
    filters: dict[str, JsonScalar]
    timeline_entries_rendered: int
    timeline_entries_total: int
    timeline_truncated: bool


class _ReportSourceDocument(TypedDict):
    completeness: str
    counters: dict[str, int]
    lane: str
    metadata: dict[str, JsonScalar]
    record_count: int
    schema_version: int | None
    session_id: str | None
    source_name: str
    summary_present: bool


class _ReportDiagnosticDocument(TypedDict):
    code: str
    lane: str | None
    message: str
    related_lane: str | None
    related_source_indices: list[int]
    severity: str
    source_index: int | None


class _ReportCorrelationDocument(TypedDict):
    basis: str
    candidate_record_indices: list[int]
    kind: str


class _ReportTimelineDocument(TypedDict):
    attributes: dict[str, JsonScalar]
    correlation: _ReportCorrelationDocument | None
    elapsed_ns: int | None
    event_type: str
    kind: str
    lane: str
    packet_index: int | None
    packet_sequence: int | None
    received_at: float | None
    source_index: int
    telemetry_timestamp_ms: int | None


class _ReportSummaryDocument(TypedDict):
    complete: bool
    compatible: bool
    diagnostic_counts: dict[str, int]
    diagnostics_total: int
    incomplete_sources: int
    source_count: int
    timeline_entries_rendered: int
    timeline_entries_total: int


class SessionReportDocument(TypedDict):
    """Stable JSON-compatible schema for one OrbitOps session report."""

    diagnostics: list[_ReportDiagnosticDocument]
    metadata: _ReportMetadataDocument
    selection: _ReportSelectionDocument
    sources: list[_ReportSourceDocument]
    summary: _ReportSummaryDocument
    timeline: list[_ReportTimelineDocument]


def _freeze_filters(filters: object) -> ImmutableFilters:
    if not isinstance(filters, Mapping):
        raise TypeError("filters must be a mapping")
    frozen: dict[str, JsonScalar] = {}
    for key, value in filters.items():
        if not isinstance(key, str) or not key:
            raise ValueError("filter names must be non-empty strings")
        if "\x00" in key:
            raise ValueError("filter names must not contain NUL characters")
        if not isinstance(value, str | int | float | bool | None):
            raise TypeError(f"filter {key!r} has an unsupported value")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"filter {key!r} must be finite")
        frozen[key] = value
    return MappingProxyType(frozen)


@dataclass(frozen=True, slots=True)
class SessionReport:
    """One immutable report projection over a complete normalized session model.

    ``session`` always retains the unfiltered source summaries and counters.
    ``timeline`` may be filtered or limited by a caller, while ``timeline_total``
    records the complete normalized entry count.
    """

    session: NormalizedSession
    timeline: tuple[TimelineEntry, ...]
    diagnostics: tuple[Diagnostic, ...]
    timeline_total: int
    filters: ImmutableFilters = field(default_factory=dict)
    truncated: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.session, NormalizedSession):
            raise TypeError("session must be a NormalizedSession")
        if not isinstance(self.timeline, tuple):
            raise TypeError("timeline must be a tuple")
        if any(not isinstance(entry, TimelineEntry) for entry in self.timeline):
            raise TypeError("timeline must contain TimelineEntry values")
        if not isinstance(self.diagnostics, tuple):
            raise TypeError("diagnostics must be a tuple")
        if any(not isinstance(item, Diagnostic) for item in self.diagnostics):
            raise TypeError("diagnostics must contain Diagnostic values")
        if isinstance(self.timeline_total, bool) or not isinstance(self.timeline_total, int):
            raise TypeError("timeline_total must be an integer")
        if self.timeline_total != len(self.session.timeline):
            raise ValueError("timeline_total must equal the normalized session entry count")
        if len(self.timeline) > self.timeline_total:
            raise ValueError("rendered timeline cannot exceed the normalized session timeline")
        session_entries = {
            (entry.lane, entry.source_index): entry for entry in self.session.timeline
        }
        if any(
            session_entries.get((entry.lane, entry.source_index)) != entry
            for entry in self.timeline
        ):
            raise ValueError("report timeline must be a projection of the normalized session")
        if tuple(sorted(self.timeline, key=lambda entry: entry.sort_key)) != self.timeline:
            raise ValueError("report timeline entries must use deterministic order")
        if tuple(sorted(self.diagnostics, key=lambda item: item.sort_key)) != self.diagnostics:
            raise ValueError("report diagnostics must use deterministic order")
        if not isinstance(self.truncated, bool):
            raise TypeError("truncated must be a boolean")
        if self.truncated and len(self.timeline) >= self.timeline_total:
            raise ValueError("truncated reports must omit at least one timeline entry")
        object.__setattr__(self, "filters", _freeze_filters(self.filters))

    @classmethod
    def from_session(cls, session: NormalizedSession) -> SessionReport:
        """Build the unfiltered report projection for one normalized session."""

        if not isinstance(session, NormalizedSession):
            raise TypeError("session must be a NormalizedSession")
        return cls(
            session=session,
            timeline=session.timeline,
            diagnostics=session.diagnostics,
            timeline_total=len(session.timeline),
        )


def _validate_packet_sequence_filter(name: str, value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer or None")
    if not 0 <= value <= _MAX_PACKET_SEQUENCE:
        raise ValueError(f"{name} must fit an unsigned 32-bit integer")
    return value


def _validate_alarm_code(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("alarm_code must be a string or None")
    normalized = value.strip()
    if not normalized:
        raise ValueError("alarm_code must be non-empty")
    if "\x00" in normalized:
        raise ValueError("alarm_code must not contain NUL characters")
    return normalized


def _validate_alarm_severity(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("alarm_severity must be a string or None")
    if value not in ALARM_SEVERITY_CHOICES:
        choices = ", ".join(ALARM_SEVERITY_CHOICES)
        raise ValueError(f"alarm_severity must be one of: {choices}")
    return value


def _validate_event_limit(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("event_limit must be an integer or None")
    if not 1 <= value <= MAX_REPORT_EVENTS:
        raise ValueError(f"event_limit must be between 1 and {MAX_REPORT_EVENTS}")
    return value


def _matches_timeline_filters(
    entry: TimelineEntry,
    *,
    packet_sequence_min: int | None,
    packet_sequence_max: int | None,
    alarm_code: str | None,
    alarm_severity: str | None,
) -> bool:
    if packet_sequence_min is not None or packet_sequence_max is not None:
        if entry.packet_sequence is None:
            return False
        if packet_sequence_min is not None and entry.packet_sequence < packet_sequence_min:
            return False
        if packet_sequence_max is not None and entry.packet_sequence > packet_sequence_max:
            return False

    if alarm_code is not None or alarm_severity is not None:
        if entry.lane is not EvidenceLane.ALARM:
            return False
        if alarm_code is not None and entry.attributes.get("code") != alarm_code:
            return False
        if alarm_severity is not None and entry.attributes.get("severity") != alarm_severity:
            return False

    return True


def project_session_report(
    session: NormalizedSession,
    *,
    packet_sequence_min: int | None = None,
    packet_sequence_max: int | None = None,
    alarm_code: str | None = None,
    alarm_severity: str | None = None,
    event_limit: int | None = None,
) -> SessionReport:
    """Build a deterministic filtered report without changing session-wide totals.

    Active filters combine with logical AND. Packet-sequence filters retain only
    entries that carry a telemetry packet sequence. Alarm filters retain only alarm
    transitions whose normalized attributes match exactly. The event limit is applied
    last, after filtering and stable timeline ordering.
    """

    if not isinstance(session, NormalizedSession):
        raise TypeError("session must be a NormalizedSession")
    sequence_min = _validate_packet_sequence_filter("packet_sequence_min", packet_sequence_min)
    sequence_max = _validate_packet_sequence_filter("packet_sequence_max", packet_sequence_max)
    if sequence_min is not None and sequence_max is not None and sequence_min > sequence_max:
        raise ValueError("packet_sequence_min must not exceed packet_sequence_max")
    code = _validate_alarm_code(alarm_code)
    severity = _validate_alarm_severity(alarm_severity)
    limit = _validate_event_limit(event_limit)

    matched = tuple(
        entry
        for entry in session.timeline
        if _matches_timeline_filters(
            entry,
            packet_sequence_min=sequence_min,
            packet_sequence_max=sequence_max,
            alarm_code=code,
            alarm_severity=severity,
        )
    )
    truncated = limit is not None and len(matched) > limit
    timeline = matched if limit is None else matched[:limit]

    diagnostics = list(session.diagnostics)
    if truncated:
        diagnostics.append(
            Diagnostic(
                DiagnosticCode.TIMELINE_TRUNCATED,
                DiagnosticSeverity.INFO,
                (
                    f"timeline rendering limited to {limit} of {len(matched)} matching "
                    f"entries; normalized session contains {len(session.timeline)} entries"
                ),
            )
        )

    filters: dict[str, JsonScalar] = {}
    for name, value in (
        ("alarm_code", code),
        ("alarm_severity", severity),
        ("event_limit", limit),
        ("packet_sequence_max", sequence_max),
        ("packet_sequence_min", sequence_min),
    ):
        if value is not None:
            filters[name] = value

    return SessionReport(
        session=session,
        timeline=timeline,
        diagnostics=tuple(sorted(diagnostics, key=lambda item: item.sort_key)),
        timeline_total=len(session.timeline),
        filters=filters,
        truncated=truncated,
    )


def _sorted_mapping(values: Mapping[str, JsonScalar]) -> dict[str, JsonScalar]:
    return {key: values[key] for key in sorted(values)}


def _source_document(summary: LaneSummary) -> _ReportSourceDocument:
    source = summary.source
    return {
        "completeness": source.completeness.value,
        "counters": {key: summary.counters[key] for key in sorted(summary.counters)},
        "lane": source.lane.value,
        "metadata": _sorted_mapping(summary.metadata),
        "record_count": source.record_count,
        "schema_version": source.schema_version,
        "session_id": source.session_id,
        "source_name": source.source_name,
        "summary_present": summary.summary_present,
    }


def _diagnostic_document(diagnostic: Diagnostic) -> _ReportDiagnosticDocument:
    return {
        "code": diagnostic.code.value,
        "lane": None if diagnostic.lane is None else diagnostic.lane.value,
        "message": diagnostic.message,
        "related_lane": (
            None if diagnostic.related_lane is None else diagnostic.related_lane.value
        ),
        "related_source_indices": list(diagnostic.related_source_indices),
        "severity": diagnostic.severity.value,
        "source_index": diagnostic.source_index,
    }


def _correlation_document(
    correlation: CorrelationDecision | None,
) -> _ReportCorrelationDocument | None:
    if correlation is None:
        return None
    return {
        "basis": correlation.basis.value,
        "candidate_record_indices": list(correlation.candidate_record_indices),
        "kind": correlation.kind.value,
    }


def _timeline_document(entry: TimelineEntry) -> _ReportTimelineDocument:
    return {
        "attributes": _sorted_mapping(entry.attributes),
        "correlation": _correlation_document(entry.correlation),
        "elapsed_ns": entry.elapsed_ns,
        "event_type": entry.event_type,
        "kind": entry.kind.value,
        "lane": entry.lane.value,
        "packet_index": entry.packet_index,
        "packet_sequence": entry.packet_sequence,
        "received_at": entry.received_at,
        "source_index": entry.source_index,
        "telemetry_timestamp_ms": entry.telemetry_timestamp_ms,
    }


def _diagnostic_counts(diagnostics: Sequence[Diagnostic]) -> dict[str, int]:
    return {
        severity.value: sum(item.severity is severity for item in diagnostics)
        for severity in DiagnosticSeverity
    }


def session_report_document(report: SessionReport) -> SessionReportDocument:
    """Return the stable JSON-compatible session report document."""

    if not isinstance(report, SessionReport):
        raise TypeError("report must be a SessionReport")
    session = report.session
    incomplete_sources = sum(
        summary.source.completeness is SourceCompleteness.INCOMPLETE for summary in session.sources
    )
    return {
        "diagnostics": [_diagnostic_document(item) for item in report.diagnostics],
        "metadata": {
            "cross_stream_provenance_verified": False,
            "evidence_bundle": EVIDENCE_BUNDLE_KIND,
            "report_format": REPORT_FORMAT,
            "report_format_version": REPORT_FORMAT_VERSION,
        },
        "selection": {
            "filters": _sorted_mapping(report.filters),
            "timeline_entries_rendered": len(report.timeline),
            "timeline_entries_total": report.timeline_total,
            "timeline_truncated": report.truncated,
        },
        "sources": [_source_document(summary) for summary in session.sources],
        "summary": {
            "complete": session.is_complete,
            "compatible": session.is_compatible,
            "diagnostic_counts": _diagnostic_counts(report.diagnostics),
            "diagnostics_total": len(report.diagnostics),
            "incomplete_sources": incomplete_sources,
            "source_count": len(session.sources),
            "timeline_entries_rendered": len(report.timeline),
            "timeline_entries_total": report.timeline_total,
        },
        "timeline": [_timeline_document(entry) for entry in report.timeline],
    }


def render_session_report_json(report: SessionReport) -> str:
    """Render deterministic, versioned JSON with one trailing newline."""

    return (
        json.dumps(
            session_report_document(report),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _format_scalar(value: JsonScalar) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _format_mapping(values: Mapping[str, JsonScalar]) -> str:
    if not values:
        return "none"
    return " ".join(f"{key}={_format_scalar(values[key])}" for key in sorted(values))


def _source_text(summary: LaneSummary) -> list[str]:
    source = summary.source
    schema = "none" if source.schema_version is None else str(source.schema_version)
    session_id = "none" if source.session_id is None else _format_scalar(source.session_id)
    return [
        (
            f"- {source.lane.value} source={_format_scalar(source.source_name)} "
            f"records={source.record_count} completeness={source.completeness.value} "
            f"schema={schema} session_id={session_id} "
            f"summary={str(summary.summary_present).lower()}"
        ),
        f"  counters: {_format_mapping(summary.counters)}",
        f"  metadata: {_format_mapping(summary.metadata)}",
    ]


def _diagnostic_text(diagnostic: Diagnostic) -> str:
    location = "session"
    if diagnostic.lane is not None:
        location = diagnostic.lane.value
        if diagnostic.source_index is not None:
            location += f"#{diagnostic.source_index}"
    related = ""
    if diagnostic.related_lane is not None:
        indices = ",".join(str(index) for index in diagnostic.related_source_indices)
        related = f" related={diagnostic.related_lane.value}[{indices}]"
    return (
        f"- {diagnostic.severity.value.upper()} {location} "
        f"{diagnostic.code.value} message={_format_scalar(diagnostic.message)}{related}"
    )


def _correlation_text(correlation: CorrelationDecision | None) -> str:
    if correlation is None:
        return "none"
    candidates = ",".join(str(index) for index in correlation.candidate_record_indices)
    suffix = "" if not candidates else f"[{candidates}]"
    return f"{correlation.kind.value}/{correlation.basis.value}{suffix}"


def _timeline_text(entry: TimelineEntry) -> str:
    fields = [
        f"- {entry.lane.value}#{entry.source_index}",
        entry.kind.value,
        entry.event_type,
    ]
    for name, value in (
        ("received_at", entry.received_at),
        ("elapsed_ns", entry.elapsed_ns),
        ("packet_sequence", entry.packet_sequence),
        ("packet_index", entry.packet_index),
        ("telemetry_timestamp_ms", entry.telemetry_timestamp_ms),
    ):
        if value is not None:
            fields.append(f"{name}={_format_scalar(value)}")
    if entry.correlation is not None:
        fields.append(f"correlation={_correlation_text(entry.correlation)}")
    fields.append(f"attributes={_format_mapping(entry.attributes)}")
    return " ".join(fields)


def render_session_report_text(report: SessionReport) -> str:
    """Render a deterministic operator-readable report with stable sections."""

    if not isinstance(report, SessionReport):
        raise TypeError("report must be a SessionReport")
    session = report.session
    lines = [
        "OrbitOps session report",
        f"format: {REPORT_FORMAT}/v{REPORT_FORMAT_VERSION}",
        (
            "status: "
            f"{'complete' if session.is_complete else 'incomplete'} "
            f"{'compatible' if session.is_compatible else 'incompatible'}"
        ),
        "evidence: operator-selected bundle; cross-stream provenance unverified",
        (
            f"timeline: {len(report.timeline)}/{report.timeline_total} entries "
            f"truncated={str(report.truncated).lower()}"
        ),
        f"filters: {_format_mapping(report.filters)}",
        "",
        "SUMMARY",
        f"sources: {len(session.sources)}",
        f"diagnostics: {len(report.diagnostics)}",
        "",
        "SOURCES",
    ]
    for summary in session.sources:
        lines.extend(_source_text(summary))

    lines.extend(["", "DIAGNOSTICS"])
    if report.diagnostics:
        lines.extend(_diagnostic_text(item) for item in report.diagnostics)
    else:
        lines.append("- none")

    lines.extend(["", "TIMELINE"])
    if report.timeline:
        lines.extend(_timeline_text(entry) for entry in report.timeline)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"

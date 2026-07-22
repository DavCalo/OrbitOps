"""Strict loading, normalization, correlation, and diagnostics for session evidence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import TypeVar

from .. import alarm_events as alarm_event_contract
from ..link import events as link_event_contract
from ..link import statistics as link_statistics_contract
from ..protocol import ProtocolError, TelemetryPacket, decode_packet
from ..recorder import RECORD_VERSION, RecordedTelemetryRecord, load_telemetry_records
from .correlation import (
    CorrelationDecision,
    CorrelationKind,
    EvidenceLane,
    classify_source_completeness,
    classify_telemetry_alarm_match,
)
from .errors import MalformedEvidenceError
from .models import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticSeverity,
    LaneSummary,
    NormalizedSession,
    SourceDescriptor,
    TimelineEntry,
    TimelineEntryKind,
)

_SourceItem = TypeVar("_SourceItem")
_MAX_PACKET_SEQUENCE = 0xFFFFFFFF
_ALARM_TRANSITION_TYPES = frozenset(
    {
        alarm_event_contract.AlarmEventType.ALARM_RAISED,
        alarm_event_contract.AlarmEventType.ALARM_UPDATED,
        alarm_event_contract.AlarmEventType.ALARM_CLEARED,
    }
)
_LINK_CONTEXT_TYPES = frozenset(
    {
        link_event_contract.LinkEventType.RUN_METADATA,
        link_event_contract.LinkEventType.RUN_SUMMARY,
    }
)


def _require_optional_path(name: str, value: object) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, Path):
        raise TypeError(f"{name} must be a pathlib.Path or None")
    return value


def _source_name(path: Path) -> str:
    return path.name or str(path)


def _load_strict(
    lane: EvidenceLane,
    path: Path,
    loader: Callable[[Path], tuple[_SourceItem, ...]],
) -> tuple[_SourceItem, ...]:
    try:
        return loader(path)
    except (TypeError, ValueError) as exc:
        raise MalformedEvidenceError(
            f"invalid {lane.value} evidence in {_source_name(path)!r}: {exc}",
            lane=lane,
            source_name=str(path),
        ) from exc


def _telemetry_attributes(packet: TelemetryPacket) -> dict[str, str | int]:
    return {
        "mode": packet.mode.name,
        "battery_mv": packet.battery_mv,
        "bus_current_ma": packet.bus_current_ma,
        "temperature_centi_c": packet.temperature_centi_c,
        "roll_centi_deg": packet.roll_centi_deg,
        "pitch_centi_deg": packet.pitch_centi_deg,
        "yaw_centi_deg": packet.yaw_centi_deg,
    }


def _translate_correlation(
    decoded_sequences: Sequence[int],
    decoded_source_indices: Sequence[int],
    packet_sequence: int,
) -> CorrelationDecision:
    decision = classify_telemetry_alarm_match(tuple(decoded_sequences), packet_sequence)
    if not decision.candidate_record_indices:
        return decision
    translated = tuple(
        decoded_source_indices[candidate] for candidate in decision.candidate_record_indices
    )
    return CorrelationDecision(
        kind=decision.kind,
        basis=decision.basis,
        candidate_record_indices=translated,
    )


def _telemetry_sequence_diagnostics(
    decoded: Sequence[tuple[int, int]],
) -> tuple[list[Diagnostic], int, int]:
    diagnostics: list[Diagnostic] = []
    indices_by_sequence: dict[int, list[int]] = defaultdict(list)
    for source_index, sequence in decoded:
        indices_by_sequence[sequence].append(source_index)

    duplicate_count = 0
    for sequence, indices in sorted(indices_by_sequence.items()):
        if len(indices) < 2:
            continue
        duplicate_count += len(indices) - 1
        related = tuple(indices)
        diagnostics.append(
            Diagnostic(
                DiagnosticCode.TELEMETRY_SEQUENCE_DUPLICATE,
                DiagnosticSeverity.WARNING,
                f"telemetry packet sequence {sequence} appears in multiple records",
                lane=EvidenceLane.TELEMETRY,
                source_index=indices[0],
                related_lane=EvidenceLane.TELEMETRY,
                related_source_indices=related,
            )
        )

    gap_count = 0
    for (previous_index, previous_sequence), (current_index, current_sequence) in pairwise(decoded):
        if current_sequence == previous_sequence:
            continue
        expected = (previous_sequence + 1) & _MAX_PACKET_SEQUENCE
        if current_sequence == expected:
            continue
        gap_count += 1
        modular_distance = (current_sequence - previous_sequence) & _MAX_PACKET_SEQUENCE
        if 1 < modular_distance <= (_MAX_PACKET_SEQUENCE + 1) // 2:
            missing = modular_distance - 1
            message = (
                f"telemetry sequence gap after {previous_sequence}: "
                f"expected {expected}, found {current_sequence}, missing {missing}"
            )
        else:
            message = (
                f"telemetry sequence is non-contiguous after {previous_sequence}: "
                f"expected {expected}, found {current_sequence}"
            )
        diagnostics.append(
            Diagnostic(
                DiagnosticCode.TELEMETRY_SEQUENCE_GAP,
                DiagnosticSeverity.WARNING,
                message,
                lane=EvidenceLane.TELEMETRY,
                source_index=current_index,
                related_lane=EvidenceLane.TELEMETRY,
                related_source_indices=(previous_index, current_index),
            )
        )

    return diagnostics, gap_count, duplicate_count


def _normalize_telemetry(
    path: Path,
    records: Sequence[RecordedTelemetryRecord],
) -> tuple[LaneSummary, list[TimelineEntry], list[Diagnostic], tuple[int, ...], tuple[int, ...]]:
    timeline: list[TimelineEntry] = []
    diagnostics: list[Diagnostic] = []
    decoded_pairs: list[tuple[int, int]] = []
    decoded_sequences: list[int] = []
    decoded_source_indices: list[int] = []
    rejected_count = 0

    for record in records:
        try:
            packet = decode_packet(record.packet)
        except ProtocolError as exc:
            rejected_count += 1
            reason = str(exc)
            timeline.append(
                TimelineEntry(
                    EvidenceLane.TELEMETRY,
                    record.record_index,
                    TimelineEntryKind.TELEMETRY_REJECTED,
                    "packet_rejected",
                    received_at=record.received_at,
                    attributes={"reason": reason},
                )
            )
            diagnostics.append(
                Diagnostic(
                    DiagnosticCode.TELEMETRY_PACKET_REJECTED,
                    DiagnosticSeverity.WARNING,
                    f"telemetry record {record.record_index} could not be decoded: {reason}",
                    lane=EvidenceLane.TELEMETRY,
                    source_index=record.record_index,
                )
            )
            continue

        decoded_pairs.append((record.record_index, packet.sequence))
        decoded_sequences.append(packet.sequence)
        decoded_source_indices.append(record.record_index)
        timeline.append(
            TimelineEntry(
                EvidenceLane.TELEMETRY,
                record.record_index,
                TimelineEntryKind.TELEMETRY_PACKET,
                "packet_decoded",
                received_at=record.received_at,
                packet_sequence=packet.sequence,
                telemetry_timestamp_ms=packet.timestamp_ms,
                attributes=_telemetry_attributes(packet),
            )
        )

    sequence_diagnostics, gap_count, duplicate_count = _telemetry_sequence_diagnostics(
        decoded_pairs
    )
    diagnostics.extend(sequence_diagnostics)
    if not records:
        diagnostics.append(
            Diagnostic(
                DiagnosticCode.SOURCE_EMPTY,
                DiagnosticSeverity.WARNING,
                "telemetry recording contains no evidence records",
                lane=EvidenceLane.TELEMETRY,
            )
        )

    completeness = classify_source_completeness(EvidenceLane.TELEMETRY, len(records))
    summary = LaneSummary(
        SourceDescriptor(
            EvidenceLane.TELEMETRY,
            _source_name(path),
            len(records),
            completeness,
            schema_version=RECORD_VERSION,
        ),
        summary_present=False,
        counters={
            "records_total": len(records),
            "packets_decoded": len(decoded_sequences),
            "packets_rejected": rejected_count,
            "sequence_gaps": gap_count,
            "sequence_duplicates": duplicate_count,
        },
    )
    return (
        summary,
        timeline,
        diagnostics,
        tuple(decoded_sequences),
        tuple(decoded_source_indices),
    )


def _alarm_metadata(events: Sequence[alarm_event_contract.AlarmEvent]) -> Mapping[str, str | int]:
    metadata = alarm_event_contract.run_metadata_from_events(events)
    if metadata is None:
        return {}
    return {
        "policy_name": metadata.policy_name,
        "policy_reference": metadata.policy_reference,
        "policy_schema_version": metadata.policy_schema_version,
        "policy_fingerprint": metadata.policy_fingerprint,
    }


def _normalize_alarm(
    path: Path,
    events: Sequence[alarm_event_contract.AlarmEvent],
    decoded_sequences: Sequence[int],
    decoded_source_indices: Sequence[int],
) -> tuple[LaneSummary, list[TimelineEntry], list[Diagnostic]]:
    timeline: list[TimelineEntry] = []
    diagnostics: list[Diagnostic] = []

    for event in events:
        if event.event_type not in _ALARM_TRANSITION_TYPES:
            continue
        if event.packet_sequence is None:
            raise AssertionError("validated alarm transition is missing packet_sequence")
        correlation = _translate_correlation(
            decoded_sequences,
            decoded_source_indices,
            event.packet_sequence,
        )
        timeline.append(
            TimelineEntry(
                EvidenceLane.ALARM,
                event.event_index,
                TimelineEntryKind.ALARM_TRANSITION,
                event.event_type.value,
                elapsed_ns=event.elapsed_ns,
                packet_sequence=event.packet_sequence,
                attributes=event.attributes,
                correlation=correlation,
            )
        )
        if correlation.kind is CorrelationKind.AMBIGUOUS:
            diagnostics.append(
                Diagnostic(
                    DiagnosticCode.ALARM_CORRELATION_AMBIGUOUS,
                    DiagnosticSeverity.ERROR,
                    (
                        f"alarm event {event.event_index} sequence {event.packet_sequence} "
                        "matches multiple telemetry records"
                    ),
                    lane=EvidenceLane.ALARM,
                    source_index=event.event_index,
                    related_lane=EvidenceLane.TELEMETRY,
                    related_source_indices=correlation.candidate_record_indices,
                )
            )
        elif correlation.kind is CorrelationKind.IMPOSSIBLE:
            diagnostics.append(
                Diagnostic(
                    DiagnosticCode.ALARM_CORRELATION_IMPOSSIBLE,
                    DiagnosticSeverity.WARNING,
                    (
                        f"alarm event {event.event_index} sequence {event.packet_sequence} "
                        "has no matching telemetry record in the loaded evidence"
                    ),
                    lane=EvidenceLane.ALARM,
                    source_index=event.event_index,
                )
            )

    summary_present = bool(
        events and events[-1].event_type is alarm_event_contract.AlarmEventType.RUN_SUMMARY
    )
    if not events:
        diagnostics.append(
            Diagnostic(
                DiagnosticCode.SOURCE_EMPTY,
                DiagnosticSeverity.WARNING,
                "alarm event stream contains no evidence records",
                lane=EvidenceLane.ALARM,
            )
        )
    elif not summary_present:
        diagnostics.append(
            Diagnostic(
                DiagnosticCode.SOURCE_SUMMARY_MISSING,
                DiagnosticSeverity.WARNING,
                "alarm event stream has no final run_summary",
                lane=EvidenceLane.ALARM,
            )
        )

    statistics = alarm_event_contract.statistics_from_events(events)
    schema_version = events[0].schema_version if events else None
    session_id = events[0].session_id if events else None
    completeness = classify_source_completeness(
        EvidenceLane.ALARM,
        len(events),
        summary_present=summary_present,
    )
    summary = LaneSummary(
        SourceDescriptor(
            EvidenceLane.ALARM,
            _source_name(path),
            len(events),
            completeness,
            schema_version=schema_version,
            session_id=session_id,
        ),
        summary_present=summary_present,
        counters={
            "transitions_raised": statistics.transitions_raised,
            "transitions_updated": statistics.transitions_updated,
            "transitions_cleared": statistics.transitions_cleared,
            "transitions_total": statistics.transitions_total,
        },
        metadata=_alarm_metadata(events),
    )
    return summary, timeline, diagnostics


def _link_metadata(
    events: Sequence[link_event_contract.LinkEvent],
) -> Mapping[str, str | int | float | bool | None]:
    if not events:
        return {}
    metadata = link_statistics_contract.run_metadata_from_events(events)
    if metadata is None:
        return {}
    return metadata.to_attributes()


def _normalize_link(
    path: Path,
    events: Sequence[link_event_contract.LinkEvent],
) -> tuple[LaneSummary, list[TimelineEntry], list[Diagnostic]]:
    timeline: list[TimelineEntry] = []
    diagnostics: list[Diagnostic] = []

    for event in events:
        if event.event_type in _LINK_CONTEXT_TYPES:
            continue
        timeline.append(
            TimelineEntry(
                EvidenceLane.LINK,
                event.event_index,
                TimelineEntryKind.LINK_EVENT,
                event.event_type.value,
                elapsed_ns=event.elapsed_ns,
                packet_index=event.packet_index,
                attributes=event.attributes,
            )
        )
        if event.event_type is link_event_contract.LinkEventType.PACKET_CORRUPTED:
            packet_context = (
                "unknown packet index"
                if event.packet_index is None
                else f"packet_index {event.packet_index}"
            )
            diagnostics.append(
                Diagnostic(
                    DiagnosticCode.LINK_CORRUPTION_OBSERVED,
                    DiagnosticSeverity.WARNING,
                    f"link corruption evidence observed for {packet_context}",
                    lane=EvidenceLane.LINK,
                    source_index=event.event_index,
                )
            )

    summary_present = bool(
        events and events[-1].event_type is link_event_contract.LinkEventType.RUN_SUMMARY
    )
    if not events:
        diagnostics.append(
            Diagnostic(
                DiagnosticCode.SOURCE_EMPTY,
                DiagnosticSeverity.WARNING,
                "link event stream contains no evidence records",
                lane=EvidenceLane.LINK,
            )
        )
    elif not summary_present:
        diagnostics.append(
            Diagnostic(
                DiagnosticCode.SOURCE_SUMMARY_MISSING,
                DiagnosticSeverity.WARNING,
                "link event stream has no final run_summary",
                lane=EvidenceLane.LINK,
            )
        )

    statistics = link_statistics_contract.statistics_from_events(events)
    schema_version = events[0].schema_version if events else None
    session_id = events[0].session_id if events else None
    completeness = classify_source_completeness(
        EvidenceLane.LINK,
        len(events),
        summary_present=summary_present,
    )
    summary = LaneSummary(
        SourceDescriptor(
            EvidenceLane.LINK,
            _source_name(path),
            len(events),
            completeness,
            schema_version=schema_version,
            session_id=session_id,
        ),
        summary_present=summary_present,
        counters=statistics.to_dict(),
        metadata=_link_metadata(events),
    )
    return summary, timeline, diagnostics


def _missing_lane_summary(lane: EvidenceLane) -> tuple[LaneSummary, Diagnostic]:
    if lane is EvidenceLane.TELEMETRY:
        completeness = classify_source_completeness(lane, 0)
        counters = {
            "records_total": 0,
            "packets_decoded": 0,
            "packets_rejected": 0,
            "sequence_gaps": 0,
            "sequence_duplicates": 0,
        }
    elif lane is EvidenceLane.ALARM:
        completeness = classify_source_completeness(lane, 0, summary_present=False)
        statistics = alarm_event_contract.statistics_from_events(())
        counters = {
            "transitions_raised": statistics.transitions_raised,
            "transitions_updated": statistics.transitions_updated,
            "transitions_cleared": statistics.transitions_cleared,
            "transitions_total": statistics.transitions_total,
        }
    else:
        completeness = classify_source_completeness(lane, 0, summary_present=False)
        counters = link_statistics_contract.statistics_from_events(()).to_dict()

    summary = LaneSummary(
        SourceDescriptor(
            lane,
            "<not provided>",
            0,
            completeness,
        ),
        summary_present=False,
        counters=counters,
    )
    diagnostic = Diagnostic(
        DiagnosticCode.SOURCE_NOT_PROVIDED,
        DiagnosticSeverity.WARNING,
        f"{lane.value} evidence source was not provided",
        lane=lane,
    )
    return summary, diagnostic


def inspect_session(
    *,
    telemetry_path: Path | None = None,
    link_events_path: Path | None = None,
    alarm_events_path: Path | None = None,
) -> NormalizedSession:
    """Build one deterministic normalized session from selected evidence sources.

    Each input is optional, but at least one source must be selected. Missing lanes
    remain explicit and incomplete in the normalized model. Malformed source content
    raises :class:`MalformedEvidenceError`; filesystem failures remain ``OSError``
    instances so callers can distinguish input/output failures from malformed data.
    """

    telemetry = _require_optional_path("telemetry_path", telemetry_path)
    link = _require_optional_path("link_events_path", link_events_path)
    alarm = _require_optional_path("alarm_events_path", alarm_events_path)
    if telemetry is None and link is None and alarm is None:
        raise ValueError("at least one evidence source must be provided")

    if telemetry is None:
        telemetry_summary, telemetry_missing = _missing_lane_summary(EvidenceLane.TELEMETRY)
        telemetry_timeline: list[TimelineEntry] = []
        telemetry_diagnostics = [telemetry_missing]
        decoded_sequences: tuple[int, ...] = ()
        decoded_source_indices: tuple[int, ...] = ()
    else:
        telemetry_records = _load_strict(
            EvidenceLane.TELEMETRY,
            telemetry,
            load_telemetry_records,
        )
        (
            telemetry_summary,
            telemetry_timeline,
            telemetry_diagnostics,
            decoded_sequences,
            decoded_source_indices,
        ) = _normalize_telemetry(telemetry, telemetry_records)

    if alarm is None:
        alarm_summary, alarm_missing = _missing_lane_summary(EvidenceLane.ALARM)
        alarm_timeline: list[TimelineEntry] = []
        alarm_diagnostics = [alarm_missing]
    else:
        alarm_records = _load_strict(
            EvidenceLane.ALARM,
            alarm,
            alarm_event_contract.load_alarm_events,
        )
        alarm_summary, alarm_timeline, alarm_diagnostics = _normalize_alarm(
            alarm,
            alarm_records,
            decoded_sequences,
            decoded_source_indices,
        )

    if link is None:
        link_summary, link_missing = _missing_lane_summary(EvidenceLane.LINK)
        link_timeline: list[TimelineEntry] = []
        link_diagnostics = [link_missing]
    else:
        link_records = _load_strict(
            EvidenceLane.LINK,
            link,
            link_event_contract.load_link_events,
        )
        if (
            link_records
            and link_records[-1].event_type is link_event_contract.LinkEventType.RUN_SUMMARY
        ):
            try:
                link_statistics_contract.validate_run_summary(link_records)
            except (TypeError, ValueError) as exc:
                raise MalformedEvidenceError(
                    f"invalid link evidence in {_source_name(link)!r}: {exc}",
                    lane=EvidenceLane.LINK,
                    source_name=str(link),
                ) from exc
        link_summary, link_timeline, link_diagnostics = _normalize_link(link, link_records)

    timeline = tuple(
        sorted(
            (*telemetry_timeline, *alarm_timeline, *link_timeline),
            key=lambda entry: entry.sort_key,
        )
    )
    diagnostics = tuple(
        sorted(
            (*telemetry_diagnostics, *alarm_diagnostics, *link_diagnostics),
            key=lambda item: item.sort_key,
        )
    )
    return NormalizedSession(
        (telemetry_summary, alarm_summary, link_summary),
        timeline,
        diagnostics,
    )

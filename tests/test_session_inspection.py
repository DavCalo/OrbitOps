from __future__ import annotations

import json
import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path

from orbitops.alarm_events import (
    AlarmEvent,
    AlarmEventType,
    AlarmRunMetadata,
    AlarmRunStatistics,
)
from orbitops.link.events import LinkEvent, LinkEventType, LinkRunMetadata
from orbitops.link.statistics import LinkStatistics
from orbitops.protocol import Mode, TelemetryPacket, encode_packet
from orbitops.recorder import SessionRecorder
from orbitops.session import (
    CorrelationKind,
    DiagnosticCode,
    DiagnosticSeverity,
    EvidenceLane,
    IncompatibleEvidenceError,
    MalformedEvidenceError,
    SourceCompleteness,
    TimelineEntryKind,
    inspect_session,
)


def _packet(sequence: int, timestamp_ms: int | None = None) -> bytes:
    return encode_packet(
        TelemetryPacket(
            sequence=sequence,
            timestamp_ms=sequence * 1000 if timestamp_ms is None else timestamp_ms,
            mode=Mode.NOMINAL,
            battery_mv=8200,
            bus_current_ma=240,
            temperature_centi_c=2100,
            roll_centi_deg=100,
            pitch_centi_deg=-200,
            yaw_centi_deg=300,
        )
    )


def _write_telemetry(path: Path, packets: Iterable[bytes]) -> None:
    with SessionRecorder(path) as recorder:
        for index, packet in enumerate(packets):
            recorder.write(packet, 100.0 + index)


def _alarm_metadata() -> AlarmRunMetadata:
    return AlarmRunMetadata(
        policy_name="standard",
        policy_reference="builtin:standard",
        policy_schema_version=1,
        policy_fingerprint="sha256:" + "1" * 64,
    )


def _alarm_transition(index: int, sequence: int) -> AlarmEvent:
    return AlarmEvent(
        session_id="alarm-run",
        event_index=index,
        elapsed_ns=index * 10,
        event_type=AlarmEventType.ALARM_RAISED,
        packet_sequence=sequence,
        attributes={
            "alarm_identity": "temperature",
            "code": "TEMP_HIGH",
            "message": "temperature exceeds threshold",
            "observed_value": 51.0,
            "severity": "warning",
            "threshold": 50.0,
        },
    )


def _write_alarm(path: Path, events: Iterable[AlarmEvent]) -> None:
    path.write_text(
        "".join(json.dumps(event.to_dict(), sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )


def _link_metadata() -> LinkRunMetadata:
    return LinkRunMetadata(
        configuration_fingerprint="sha256:" + "2" * 64,
        profile_name="nominal",
        profile_reference="builtin:nominal",
        profile_schema_version=1,
    )


def _write_link(path: Path, events: Iterable[LinkEvent]) -> None:
    path.write_text(
        "".join(json.dumps(event.to_dict(), sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )


class SessionInspectionTests(unittest.TestCase):
    def paths(self, directory: str) -> tuple[Path, Path, Path]:
        root = Path(directory)
        return root / "telemetry.jsonl", root / "link.jsonl", root / "alarm.jsonl"

    def complete_alarm_events(self, sequence: int) -> tuple[AlarmEvent, ...]:
        metadata = AlarmEvent(
            session_id="alarm-run",
            event_index=0,
            elapsed_ns=0,
            event_type=AlarmEventType.RUN_METADATA,
            attributes=_alarm_metadata().to_attributes(),
        )
        transition = _alarm_transition(1, sequence)
        summary = AlarmEvent(
            session_id="alarm-run",
            event_index=2,
            elapsed_ns=20,
            event_type=AlarmEventType.RUN_SUMMARY,
            attributes=AlarmRunStatistics(transitions_raised=1).to_attributes(),
        )
        return metadata, transition, summary

    def complete_link_events(self) -> tuple[LinkEvent, ...]:
        metadata = LinkEvent(
            session_id="link-run",
            event_index=0,
            elapsed_ns=0,
            event_type=LinkEventType.RUN_METADATA,
            attributes=_link_metadata().to_attributes(),
        )
        received = LinkEvent(
            session_id="link-run",
            event_index=1,
            elapsed_ns=5,
            event_type=LinkEventType.PACKET_RECEIVED,
            packet_index=0,
        )
        corrupted = LinkEvent(
            session_id="link-run",
            event_index=2,
            elapsed_ns=6,
            event_type=LinkEventType.PACKET_CORRUPTED,
            packet_index=0,
        )
        summary = LinkEvent(
            session_id="link-run",
            event_index=3,
            elapsed_ns=7,
            event_type=LinkEventType.RUN_SUMMARY,
            attributes=LinkStatistics(
                packets_received=1,
                packets_corrupted=1,
            ).to_dict(),
        )
        return metadata, received, corrupted, summary

    def test_complete_sources_produce_correlated_deterministic_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            telemetry, link, alarm = self.paths(directory)
            _write_telemetry(telemetry, (_packet(10), _packet(11)))
            _write_alarm(alarm, self.complete_alarm_events(11))
            _write_link(link, self.complete_link_events())

            session = inspect_session(
                telemetry_path=telemetry,
                link_events_path=link,
                alarm_events_path=alarm,
            )

        self.assertTrue(session.is_complete)
        self.assertTrue(session.is_compatible)
        self.assertEqual(
            tuple(summary.source.lane for summary in session.sources),
            (EvidenceLane.TELEMETRY, EvidenceLane.ALARM, EvidenceLane.LINK),
        )
        self.assertEqual(
            [(entry.lane, entry.source_index) for entry in session.timeline],
            [
                (EvidenceLane.TELEMETRY, 0),
                (EvidenceLane.TELEMETRY, 1),
                (EvidenceLane.ALARM, 1),
                (EvidenceLane.LINK, 1),
                (EvidenceLane.LINK, 2),
            ],
        )
        alarm_entry = session.timeline[2]
        self.assertIsNotNone(alarm_entry.correlation)
        assert alarm_entry.correlation is not None
        self.assertEqual(alarm_entry.correlation.kind, CorrelationKind.EXACT)
        self.assertEqual(alarm_entry.correlation.candidate_record_indices, (1,))
        self.assertEqual(
            [diagnostic.code for diagnostic in session.diagnostics],
            [DiagnosticCode.LINK_CORRUPTION_OBSERVED],
        )
        self.assertEqual(session.sources[0].counters["packets_decoded"], 2)
        self.assertEqual(session.sources[1].counters["transitions_total"], 1)
        self.assertEqual(session.sources[2].counters["packets_corrupted"], 1)

    def test_all_empty_sources_produce_explicit_empty_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            telemetry, link, alarm = self.paths(directory)
            for path in (telemetry, link, alarm):
                path.write_text("", encoding="utf-8")

            session = inspect_session(
                telemetry_path=telemetry,
                link_events_path=link,
                alarm_events_path=alarm,
            )

        self.assertEqual(
            [diagnostic.code for diagnostic in session.diagnostics],
            [
                DiagnosticCode.SOURCE_EMPTY,
                DiagnosticCode.SOURCE_EMPTY,
                DiagnosticCode.SOURCE_EMPTY,
            ],
        )
        self.assertEqual(session.timeline, ())
        self.assertFalse(session.is_complete)

    def test_sequence_wraparound_is_contiguous(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            telemetry, link, alarm = self.paths(directory)
            _write_telemetry(telemetry, (_packet(0xFFFFFFFF), _packet(0)))
            _write_alarm(alarm, self.complete_alarm_events(0))
            _write_link(link, self.complete_link_events())

            session = inspect_session(
                telemetry_path=telemetry,
                link_events_path=link,
                alarm_events_path=alarm,
            )

        self.assertNotIn(
            DiagnosticCode.TELEMETRY_SEQUENCE_GAP,
            {diagnostic.code for diagnostic in session.diagnostics},
        )

    def test_legacy_link_schema_remains_readable_without_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            telemetry, link, alarm = self.paths(directory)
            _write_telemetry(telemetry, (_packet(1),))
            _write_alarm(alarm, self.complete_alarm_events(1))
            _write_link(
                link,
                (
                    LinkEvent(
                        session_id="legacy-link",
                        event_index=0,
                        elapsed_ns=0,
                        event_type=LinkEventType.PACKET_RECEIVED,
                        packet_index=0,
                        schema_version=1,
                    ),
                    LinkEvent(
                        session_id="legacy-link",
                        event_index=1,
                        elapsed_ns=1,
                        event_type=LinkEventType.RUN_SUMMARY,
                        attributes=LinkStatistics(packets_received=1).to_dict(),
                        schema_version=1,
                    ),
                ),
            )

            session = inspect_session(
                telemetry_path=telemetry,
                link_events_path=link,
                alarm_events_path=alarm,
            )

        link_summary = session.sources[2]
        self.assertEqual(link_summary.source.schema_version, 1)
        self.assertEqual(dict(link_summary.metadata), {})
        self.assertEqual(link_summary.counters["packets_received"], 1)

    def test_path_arguments_must_be_path_objects(self) -> None:
        with self.assertRaisesRegex(TypeError, "telemetry_path"):
            inspect_session(
                telemetry_path="telemetry.jsonl",  # type: ignore[arg-type]
                link_events_path=Path("link.jsonl"),
                alarm_events_path=Path("alarm.jsonl"),
            )

    def test_empty_and_interrupted_sources_remain_inspectable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            telemetry, link, alarm = self.paths(directory)
            telemetry.write_text("", encoding="utf-8")
            _write_alarm(
                alarm,
                (
                    AlarmEvent(
                        session_id="alarm-run",
                        event_index=0,
                        elapsed_ns=0,
                        event_type=AlarmEventType.RUN_METADATA,
                        attributes=_alarm_metadata().to_attributes(),
                    ),
                ),
            )
            _write_link(
                link,
                (
                    LinkEvent(
                        session_id="link-run",
                        event_index=0,
                        elapsed_ns=0,
                        event_type=LinkEventType.RUN_METADATA,
                        attributes=_link_metadata().to_attributes(),
                    ),
                ),
            )

            session = inspect_session(
                telemetry_path=telemetry,
                link_events_path=link,
                alarm_events_path=alarm,
            )

        self.assertFalse(session.is_complete)
        self.assertTrue(session.is_compatible)
        self.assertEqual(
            tuple(summary.source.completeness for summary in session.sources),
            (
                SourceCompleteness.INCOMPLETE,
                SourceCompleteness.INCOMPLETE,
                SourceCompleteness.INCOMPLETE,
            ),
        )
        self.assertEqual(
            [diagnostic.code for diagnostic in session.diagnostics],
            [
                DiagnosticCode.SOURCE_EMPTY,
                DiagnosticCode.SOURCE_SUMMARY_MISSING,
                DiagnosticCode.SOURCE_SUMMARY_MISSING,
            ],
        )

    def test_rejected_gap_and_duplicate_telemetry_are_diagnosed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            telemetry, link, alarm = self.paths(directory)
            _write_telemetry(telemetry, (_packet(1), b"invalid", _packet(3), _packet(3)))
            _write_alarm(alarm, self.complete_alarm_events(3))
            _write_link(link, self.complete_link_events())

            session = inspect_session(
                telemetry_path=telemetry,
                link_events_path=link,
                alarm_events_path=alarm,
            )

        telemetry_entries = [
            entry for entry in session.timeline if entry.lane is EvidenceLane.TELEMETRY
        ]
        self.assertEqual(
            [entry.kind for entry in telemetry_entries],
            [
                TimelineEntryKind.TELEMETRY_PACKET,
                TimelineEntryKind.TELEMETRY_REJECTED,
                TimelineEntryKind.TELEMETRY_PACKET,
                TimelineEntryKind.TELEMETRY_PACKET,
            ],
        )
        codes = [diagnostic.code for diagnostic in session.diagnostics]
        self.assertIn(DiagnosticCode.TELEMETRY_PACKET_REJECTED, codes)
        self.assertIn(DiagnosticCode.TELEMETRY_SEQUENCE_GAP, codes)
        self.assertIn(DiagnosticCode.TELEMETRY_SEQUENCE_DUPLICATE, codes)
        self.assertFalse(session.is_compatible)
        with self.assertRaises(IncompatibleEvidenceError):
            session.require_compatible()

    def test_alarm_candidates_preserve_original_telemetry_source_indices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            telemetry, link, alarm = self.paths(directory)
            _write_telemetry(telemetry, (b"invalid", _packet(5)))
            _write_alarm(alarm, self.complete_alarm_events(5))
            _write_link(link, self.complete_link_events())

            session = inspect_session(
                telemetry_path=telemetry,
                link_events_path=link,
                alarm_events_path=alarm,
            )

        alarm_entry = next(entry for entry in session.timeline if entry.lane is EvidenceLane.ALARM)
        self.assertIsNotNone(alarm_entry.correlation)
        assert alarm_entry.correlation is not None
        self.assertEqual(alarm_entry.correlation.candidate_record_indices, (1,))

    def test_impossible_alarm_correlation_is_visible_but_not_fabricated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            telemetry, link, alarm = self.paths(directory)
            _write_telemetry(telemetry, (_packet(1),))
            _write_alarm(alarm, self.complete_alarm_events(9))
            _write_link(link, self.complete_link_events())

            session = inspect_session(
                telemetry_path=telemetry,
                link_events_path=link,
                alarm_events_path=alarm,
            )

        alarm_entry = next(entry for entry in session.timeline if entry.lane is EvidenceLane.ALARM)
        self.assertIsNotNone(alarm_entry.correlation)
        assert alarm_entry.correlation is not None
        self.assertEqual(alarm_entry.correlation.kind, CorrelationKind.IMPOSSIBLE)
        diagnostic = next(
            item
            for item in session.diagnostics
            if item.code is DiagnosticCode.ALARM_CORRELATION_IMPOSSIBLE
        )
        self.assertEqual(diagnostic.severity, DiagnosticSeverity.WARNING)
        self.assertTrue(session.is_compatible)

    def test_invalid_telemetry_record_is_wrapped_as_malformed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            telemetry, link, alarm = self.paths(directory)
            telemetry.write_text("{\n", encoding="utf-8")
            _write_alarm(alarm, self.complete_alarm_events(1))
            _write_link(link, self.complete_link_events())

            with self.assertRaises(MalformedEvidenceError) as context:
                inspect_session(
                    telemetry_path=telemetry,
                    link_events_path=link,
                    alarm_events_path=alarm,
                )

        self.assertEqual(context.exception.lane, EvidenceLane.TELEMETRY)
        self.assertEqual(context.exception.source_name, str(telemetry))

    def test_invalid_link_summary_is_a_malformed_source_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            telemetry, link, alarm = self.paths(directory)
            _write_telemetry(telemetry, (_packet(1),))
            _write_alarm(alarm, self.complete_alarm_events(1))
            events = list(self.complete_link_events())
            events[-1] = LinkEvent(
                session_id="link-run",
                event_index=3,
                elapsed_ns=7,
                event_type=LinkEventType.RUN_SUMMARY,
                attributes=LinkStatistics().to_dict(),
            )
            _write_link(link, events)

            with self.assertRaises(MalformedEvidenceError) as context:
                inspect_session(
                    telemetry_path=telemetry,
                    link_events_path=link,
                    alarm_events_path=alarm,
                )

        self.assertEqual(context.exception.lane, EvidenceLane.LINK)
        self.assertEqual(context.exception.source_name, str(link))

    def test_independent_session_ids_do_not_create_metadata_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            telemetry, link, alarm = self.paths(directory)
            _write_telemetry(telemetry, (_packet(1),))
            _write_alarm(alarm, self.complete_alarm_events(1))
            _write_link(link, self.complete_link_events())

            session = inspect_session(
                telemetry_path=telemetry,
                link_events_path=link,
                alarm_events_path=alarm,
            )

        self.assertNotIn(
            DiagnosticCode.METADATA_MISMATCH,
            {diagnostic.code for diagnostic in session.diagnostics},
        )
        self.assertNotEqual(
            session.sources[1].source.session_id,
            session.sources[2].source.session_id,
        )

    def test_optional_sources_remain_explicitly_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            telemetry, _, _ = self.paths(directory)
            _write_telemetry(telemetry, (_packet(4),))

            session = inspect_session(telemetry_path=telemetry)

        self.assertFalse(session.is_complete)
        self.assertTrue(session.is_compatible)
        self.assertEqual(
            [summary.source.source_name for summary in session.sources],
            ["telemetry.jsonl", "<not provided>", "<not provided>"],
        )
        self.assertEqual(
            [diagnostic.code for diagnostic in session.diagnostics],
            [
                DiagnosticCode.SOURCE_NOT_PROVIDED,
                DiagnosticCode.SOURCE_NOT_PROVIDED,
            ],
        )

    def test_at_least_one_evidence_source_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one evidence source"):
            inspect_session()

    def test_filesystem_failures_are_not_misclassified_as_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing-telemetry.jsonl"
            with self.assertRaises(FileNotFoundError):
                inspect_session(telemetry_path=missing)


if __name__ == "__main__":
    unittest.main()

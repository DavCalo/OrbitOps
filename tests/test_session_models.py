from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orbitops.recorder import SessionRecorder, iter_records, load_telemetry_records
from orbitops.session import (
    CorrelationBasis,
    CorrelationDecision,
    CorrelationKind,
    Diagnostic,
    DiagnosticCode,
    DiagnosticSeverity,
    EvidenceLane,
    IncompatibleEvidenceError,
    IncompleteEvidenceError,
    LaneSummary,
    NormalizedSession,
    SourceCompleteness,
    SourceDescriptor,
    TimelineEntry,
    TimelineEntryKind,
)


class TelemetryLoadingTests(unittest.TestCase):
    def test_non_realtime_loader_reuses_strict_record_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.jsonl"
            with SessionRecorder(path) as recorder:
                recorder.write(b"first", 10.0)
                recorder.write(b"second", 10.5)
            path.write_text(
                path.read_text(encoding="utf-8").splitlines()[0]
                + "\n\n"
                + path.read_text(encoding="utf-8").splitlines()[1]
                + "\n",
                encoding="utf-8",
            )

            with patch("orbitops.recorder.time.sleep") as sleep:
                records = load_telemetry_records(path)

            self.assertEqual([record.record_index for record in records], [0, 1])
            self.assertEqual([record.line_number for record in records], [1, 3])
            self.assertEqual([record.received_at for record in records], [10.0, 10.5])
            self.assertEqual([record.packet for record in records], [b"first", b"second"])
            sleep.assert_not_called()

            with patch("orbitops.recorder.time.sleep") as replay_sleep:
                self.assertEqual(list(iter_records(path, speed=2.0)), [b"first", b"second"])
            replay_sleep.assert_called_once_with(0.25)

    def test_non_realtime_loader_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.jsonl"
            path.write_text("{\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid record at line 1"):
                load_telemetry_records(path)

    def test_non_realtime_loader_rejects_schema_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "record_version": 1,
                        "received_at": 1.0,
                        "packet_hex": "00",
                        "unexpected": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "invalid keys"):
                load_telemetry_records(path)


class SessionModelTests(unittest.TestCase):
    def source_summaries(self, *, link_complete: bool = True) -> tuple[LaneSummary, ...]:
        telemetry = LaneSummary(
            SourceDescriptor(
                EvidenceLane.TELEMETRY,
                "telemetry.jsonl",
                1,
                SourceCompleteness.UNKNOWN,
                schema_version=1,
            ),
            summary_present=False,
            counters={"records_total": 1, "packets_decoded": 1},
        )
        alarm = LaneSummary(
            SourceDescriptor(
                EvidenceLane.ALARM,
                "alarm.jsonl",
                2,
                SourceCompleteness.COMPLETE,
                schema_version=1,
                session_id="alarm-1",
            ),
            summary_present=True,
            counters={"transitions_raised": 0},
        )
        link = LaneSummary(
            SourceDescriptor(
                EvidenceLane.LINK,
                "link.jsonl",
                2 if link_complete else 1,
                SourceCompleteness.COMPLETE if link_complete else SourceCompleteness.INCOMPLETE,
                schema_version=2,
                session_id="link-1",
            ),
            summary_present=link_complete,
            counters={"packets_received": 0},
        )
        return telemetry, alarm, link

    def test_lane_summary_is_immutable_and_checks_completeness(self) -> None:
        summary = self.source_summaries()[0]
        with self.assertRaises(TypeError):
            summary.counters["records_total"] = 2  # type: ignore[index]
        with self.assertRaises(ValueError):
            LaneSummary(
                SourceDescriptor(
                    EvidenceLane.ALARM,
                    "alarm.jsonl",
                    1,
                    SourceCompleteness.COMPLETE,
                    schema_version=1,
                    session_id="alarm-1",
                ),
                summary_present=False,
            )

    def test_telemetry_entries_keep_wall_clock_fields_source_local(self) -> None:
        entry = TimelineEntry(
            EvidenceLane.TELEMETRY,
            0,
            TimelineEntryKind.TELEMETRY_PACKET,
            "packet_received",
            received_at=1.25,
            packet_sequence=7,
            telemetry_timestamp_ms=1000,
            attributes={"mode": "NOMINAL"},
        )
        self.assertEqual(entry.sort_key, (0, 0))
        with self.assertRaises(TypeError):
            entry.attributes["mode"] = "SAFE"  # type: ignore[index]
        with self.assertRaises(ValueError):
            TimelineEntry(
                EvidenceLane.TELEMETRY,
                0,
                TimelineEntryKind.TELEMETRY_PACKET,
                "packet_received",
                received_at=1.25,
                elapsed_ns=1,
                packet_sequence=7,
                telemetry_timestamp_ms=1000,
            )

    def test_alarm_entries_require_visible_correlation(self) -> None:
        exact = CorrelationDecision(
            CorrelationKind.EXACT,
            CorrelationBasis.PACKET_SEQUENCE,
            (0,),
        )
        entry = TimelineEntry(
            EvidenceLane.ALARM,
            1,
            TimelineEntryKind.ALARM_TRANSITION,
            "alarm_raised",
            elapsed_ns=5,
            packet_sequence=7,
            correlation=exact,
        )
        self.assertEqual(entry.sort_key, (1, 1))
        with self.assertRaises(ValueError):
            TimelineEntry(
                EvidenceLane.ALARM,
                1,
                TimelineEntryKind.ALARM_TRANSITION,
                "alarm_raised",
                elapsed_ns=5,
                packet_sequence=7,
            )

    def test_link_entries_cannot_claim_cross_lane_packet_sequence(self) -> None:
        with self.assertRaises(ValueError):
            TimelineEntry(
                EvidenceLane.LINK,
                0,
                TimelineEntryKind.LINK_EVENT,
                "packet_received",
                elapsed_ns=0,
                packet_sequence=0,
                packet_index=0,
            )

    def test_normalized_session_requires_stable_lane_and_entry_order(self) -> None:
        telemetry_entry = TimelineEntry(
            EvidenceLane.TELEMETRY,
            0,
            TimelineEntryKind.TELEMETRY_REJECTED,
            "packet_rejected",
            received_at=1.0,
            attributes={"reason": "CRC mismatch"},
        )
        diagnostic = Diagnostic(
            DiagnosticCode.TELEMETRY_PACKET_REJECTED,
            DiagnosticSeverity.WARNING,
            "telemetry packet could not be decoded",
            lane=EvidenceLane.TELEMETRY,
            source_index=0,
        )
        session = NormalizedSession(
            self.source_summaries(),
            (telemetry_entry,),
            (diagnostic,),
        )
        self.assertTrue(session.is_complete)

        with self.assertRaises(ValueError):
            NormalizedSession(
                tuple(reversed(self.source_summaries())),
                (telemetry_entry,),
                (diagnostic,),
            )

    def test_incomplete_source_is_reportable_and_enforceable(self) -> None:
        diagnostic = Diagnostic(
            DiagnosticCode.SOURCE_SUMMARY_MISSING,
            DiagnosticSeverity.WARNING,
            "link stream has no final summary",
            lane=EvidenceLane.LINK,
        )
        session = NormalizedSession(
            self.source_summaries(link_complete=False),
            (),
            (diagnostic,),
        )
        self.assertFalse(session.is_complete)
        with self.assertRaises(IncompleteEvidenceError):
            session.require_complete()

    def test_diagnostic_related_indices_must_be_unique_and_sorted(self) -> None:
        with self.assertRaises(ValueError):
            Diagnostic(
                DiagnosticCode.TELEMETRY_SEQUENCE_DUPLICATE,
                DiagnosticSeverity.WARNING,
                "duplicate sequence",
                lane=EvidenceLane.TELEMETRY,
                related_source_indices=(2, 1),
            )

    def test_cross_lane_diagnostic_relationship_is_explicit(self) -> None:
        diagnostic = Diagnostic(
            DiagnosticCode.ALARM_CORRELATION_AMBIGUOUS,
            DiagnosticSeverity.ERROR,
            "alarm sequence matches multiple telemetry records",
            lane=EvidenceLane.ALARM,
            source_index=1,
            related_lane=EvidenceLane.TELEMETRY,
            related_source_indices=(0, 2),
        )
        self.assertEqual(diagnostic.related_lane, EvidenceLane.TELEMETRY)
        self.assertEqual(diagnostic.related_source_indices, (0, 2))

    def test_error_diagnostic_marks_session_incompatible(self) -> None:
        diagnostic = Diagnostic(
            DiagnosticCode.ALARM_CORRELATION_AMBIGUOUS,
            DiagnosticSeverity.ERROR,
            "alarm sequence matches multiple telemetry records",
            lane=EvidenceLane.ALARM,
            source_index=1,
            related_lane=EvidenceLane.TELEMETRY,
            related_source_indices=(0, 2),
        )
        session = NormalizedSession(
            self.source_summaries(),
            (),
            (diagnostic,),
        )
        self.assertFalse(session.is_compatible)
        with self.assertRaises(IncompatibleEvidenceError):
            session.require_compatible()


if __name__ == "__main__":
    unittest.main()

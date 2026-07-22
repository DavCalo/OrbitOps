from __future__ import annotations

import json
import unittest

from orbitops.session.correlation import (
    CorrelationBasis,
    CorrelationDecision,
    CorrelationKind,
    EvidenceLane,
    SourceCompleteness,
)
from orbitops.session.models import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticSeverity,
    LaneSummary,
    NormalizedSession,
    SourceDescriptor,
    TimelineEntry,
    TimelineEntryKind,
)
from orbitops.session.reporting import (
    EVIDENCE_BUNDLE_KIND,
    REPORT_FORMAT,
    REPORT_FORMAT_VERSION,
    SessionReport,
    render_session_report_json,
    render_session_report_text,
    session_report_document,
)


def sample_session() -> NormalizedSession:
    sources = (
        LaneSummary(
            SourceDescriptor(
                EvidenceLane.TELEMETRY,
                "telemetry.jsonl",
                2,
                SourceCompleteness.UNKNOWN,
                schema_version=1,
            ),
            False,
            counters={"records_total": 2, "packets_decoded": 2},
        ),
        LaneSummary(
            SourceDescriptor(
                EvidenceLane.ALARM,
                "alarm.jsonl",
                3,
                SourceCompleteness.COMPLETE,
                schema_version=1,
                session_id="alarm-run",
            ),
            True,
            counters={"transitions_total": 1},
            metadata={"policy_name": "standard"},
        ),
        LaneSummary(
            SourceDescriptor(
                EvidenceLane.LINK,
                "link.jsonl",
                4,
                SourceCompleteness.COMPLETE,
                schema_version=2,
                session_id="link-run",
            ),
            True,
            counters={"packets_corrupted": 1, "packets_received": 1},
            metadata={"profile_name": "nominal"},
        ),
    )
    timeline = (
        TimelineEntry(
            EvidenceLane.TELEMETRY,
            0,
            TimelineEntryKind.TELEMETRY_PACKET,
            "packet_decoded",
            received_at=100.0,
            packet_sequence=10,
            telemetry_timestamp_ms=10000,
            attributes={"mode": "NOMINAL"},
        ),
        TimelineEntry(
            EvidenceLane.TELEMETRY,
            1,
            TimelineEntryKind.TELEMETRY_PACKET,
            "packet_decoded",
            received_at=101.0,
            packet_sequence=11,
            telemetry_timestamp_ms=11000,
            attributes={"mode": "NOMINAL"},
        ),
        TimelineEntry(
            EvidenceLane.ALARM,
            1,
            TimelineEntryKind.ALARM_TRANSITION,
            "alarm_raised",
            elapsed_ns=10,
            packet_sequence=11,
            attributes={"code": "TEMP_HIGH", "severity": "warning"},
            correlation=CorrelationDecision(
                CorrelationKind.EXACT,
                CorrelationBasis.PACKET_SEQUENCE,
                (1,),
            ),
        ),
        TimelineEntry(
            EvidenceLane.LINK,
            1,
            TimelineEntryKind.LINK_EVENT,
            "packet_received",
            elapsed_ns=5,
            packet_index=0,
        ),
    )
    diagnostics = (
        Diagnostic(
            DiagnosticCode.LINK_CORRUPTION_OBSERVED,
            DiagnosticSeverity.WARNING,
            "link corruption evidence observed for packet_index 0",
            lane=EvidenceLane.LINK,
            source_index=2,
        ),
    )
    return NormalizedSession(sources, timeline, diagnostics)


class SessionReportingTests(unittest.TestCase):
    def test_full_report_has_stable_versioned_document(self) -> None:
        report = SessionReport.from_session(sample_session())
        document = session_report_document(report)

        self.assertEqual(
            document["metadata"],
            {
                "cross_stream_provenance_verified": False,
                "evidence_bundle": EVIDENCE_BUNDLE_KIND,
                "report_format": REPORT_FORMAT,
                "report_format_version": REPORT_FORMAT_VERSION,
            },
        )
        self.assertEqual(document["summary"]["timeline_entries_total"], 4)
        self.assertEqual(document["summary"]["compatible"], True)
        self.assertEqual(document["selection"]["filters"], {})
        self.assertEqual(document["sources"][0]["lane"], "telemetry")
        correlation = document["timeline"][2]["correlation"]
        self.assertIsNotNone(correlation)
        assert correlation is not None
        self.assertEqual(correlation["kind"], "exact")

    def test_json_rendering_is_deterministic_and_machine_readable(self) -> None:
        report = SessionReport.from_session(sample_session())
        first = render_session_report_json(report)
        second = render_session_report_json(report)

        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))
        document = json.loads(first)
        self.assertEqual(document["metadata"]["report_format_version"], 1)
        self.assertNotIn("packet", document["timeline"][0]["attributes"])

    def test_text_rendering_has_stable_operator_sections(self) -> None:
        report = SessionReport.from_session(sample_session())
        rendered = render_session_report_text(report)

        expected_lines = [
            "OrbitOps session report",
            "format: orbitops.session_report/v1",
            "status: complete compatible",
            "evidence: operator-selected bundle; cross-stream provenance unverified",
            "timeline: 4/4 entries truncated=false",
            "filters: none",
            "",
            "SUMMARY",
            "sources: 3",
            "diagnostics: 1",
            "",
            "SOURCES",
            (
                '- telemetry source="telemetry.jsonl" records=2 completeness=unknown '
                "schema=1 session_id=none summary=false"
            ),
            "  counters: packets_decoded=2 records_total=2",
            "  metadata: none",
            (
                '- alarm source="alarm.jsonl" records=3 completeness=complete '
                'schema=1 session_id="alarm-run" summary=true'
            ),
            "  counters: transitions_total=1",
            '  metadata: policy_name="standard"',
            (
                '- link source="link.jsonl" records=4 completeness=complete '
                'schema=2 session_id="link-run" summary=true'
            ),
            "  counters: packets_corrupted=1 packets_received=1",
            '  metadata: profile_name="nominal"',
            "",
            "DIAGNOSTICS",
            (
                "- WARNING link#2 link_corruption_observed "
                'message="link corruption evidence observed for packet_index 0"'
            ),
            "",
            "TIMELINE",
            (
                "- telemetry#0 telemetry_packet packet_decoded received_at=100.0 "
                'packet_sequence=10 telemetry_timestamp_ms=10000 attributes=mode="NOMINAL"'
            ),
            (
                "- telemetry#1 telemetry_packet packet_decoded received_at=101.0 "
                'packet_sequence=11 telemetry_timestamp_ms=11000 attributes=mode="NOMINAL"'
            ),
            (
                "- alarm#1 alarm_transition alarm_raised elapsed_ns=10 packet_sequence=11 "
                'correlation=exact/packet_sequence[1] attributes=code="TEMP_HIGH" '
                'severity="warning"'
            ),
            ("- link#1 link_event packet_received elapsed_ns=5 packet_index=0 attributes=none"),
        ]
        self.assertEqual(rendered, "\n".join(expected_lines) + "\n")

    def test_text_escapes_untrusted_diagnostic_controls(self) -> None:
        session = sample_session()
        diagnostic = Diagnostic(
            DiagnosticCode.LINK_CORRUPTION_OBSERVED,
            DiagnosticSeverity.WARNING,
            "line one\nline two\x1b[31m",
            lane=EvidenceLane.LINK,
            source_index=2,
        )
        adjusted = NormalizedSession(session.sources, session.timeline, (diagnostic,))

        rendered = render_session_report_text(SessionReport.from_session(adjusted))

        self.assertIn('message="line one\\nline two\\u001b[31m"', rendered)
        self.assertNotIn("line one\nline two", rendered)

    def test_projection_preserves_unfiltered_session_totals(self) -> None:
        session = sample_session()
        report = SessionReport(
            session=session,
            timeline=session.timeline[:2],
            diagnostics=session.diagnostics,
            timeline_total=len(session.timeline),
            filters={"sequence_min": 10, "sequence_max": 11},
        )
        document = session_report_document(report)

        self.assertEqual(document["selection"]["timeline_entries_rendered"], 2)
        self.assertEqual(document["selection"]["timeline_entries_total"], 4)
        self.assertEqual(document["sources"][0]["counters"]["records_total"], 2)

    def test_report_projection_is_immutable_and_validated(self) -> None:
        session = sample_session()
        report = SessionReport.from_session(session)
        with self.assertRaises(TypeError):
            report.filters["limit"] = 1  # type: ignore[index]
        with self.assertRaises(ValueError):
            SessionReport(
                session=session,
                timeline=session.timeline,
                diagnostics=session.diagnostics,
                timeline_total=3,
            )
        with self.assertRaises(ValueError):
            SessionReport(
                session=session,
                timeline=session.timeline,
                diagnostics=session.diagnostics,
                timeline_total=4,
                truncated=True,
            )


if __name__ == "__main__":
    unittest.main()

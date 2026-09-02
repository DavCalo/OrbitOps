from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.session import DiagnosticCode, EvidenceLane, inspect_session  # noqa: E402

SAMPLE = ROOT / "examples" / "session-inspection"


class SessionInspectionSampleTests(unittest.TestCase):
    def test_supported_sample_bundle_remains_complete_and_inspectable(self) -> None:
        session = inspect_session(
            telemetry_path=SAMPLE / "telemetry.jsonl",
            link_events_path=SAMPLE / "link-events.jsonl",
            alarm_events_path=SAMPLE / "alarm-events.jsonl",
        )

        self.assertTrue(session.is_complete)
        self.assertTrue(session.is_compatible)
        self.assertEqual(len(session.timeline), 5)
        self.assertEqual(
            [diagnostic.code for diagnostic in session.diagnostics],
            [DiagnosticCode.LINK_CORRUPTION_OBSERVED],
        )

        sources = {summary.source.lane: summary for summary in session.sources}
        self.assertEqual(sources[EvidenceLane.TELEMETRY].counters["packets_decoded"], 2)
        self.assertEqual(sources[EvidenceLane.ALARM].counters["transitions_total"], 1)
        self.assertEqual(sources[EvidenceLane.LINK].counters["packets_corrupted"], 1)

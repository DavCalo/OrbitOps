from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT / "ground_station"))
sys.path.insert(0, str(SCRIPTS))

from orbitops.session import inspect_session  # noqa: E402
from orbitops.session.inspection import (  # noqa: E402
    _load_session_evidence,
    _normalize_loaded_session,
)
from session_benchmark_support import (  # noqa: E402
    DATASET_SCALES,
    dataset_paths,
    normalize_peak_rss_bytes,
    write_dataset,
)


class SessionBenchmarkDatasetTests(unittest.TestCase):
    def test_small_dataset_is_byte_deterministic_and_complete(self) -> None:
        scale = DATASET_SCALES["small"]
        with (
            tempfile.TemporaryDirectory() as left_name,
            tempfile.TemporaryDirectory() as right_name,
        ):
            left = Path(left_name)
            right = Path(right_name)
            left_manifest = write_dataset(left, scale)
            right_manifest = write_dataset(right, scale)

            self.assertEqual(left_manifest, right_manifest)
            left_paths = dataset_paths(left)
            right_paths = dataset_paths(right)
            for left_path, right_path in (
                (left_paths.telemetry, right_paths.telemetry),
                (left_paths.alarm_events, right_paths.alarm_events),
                (left_paths.link_events, right_paths.link_events),
                (left_paths.manifest, right_paths.manifest),
            ):
                self.assertEqual(left_path.read_bytes(), right_path.read_bytes())

            session = inspect_session(
                telemetry_path=left_paths.telemetry,
                link_events_path=left_paths.link_events,
                alarm_events_path=left_paths.alarm_events,
            )

        self.assertTrue(session.is_complete)
        self.assertTrue(session.is_compatible)
        self.assertEqual(
            len(session.timeline),
            left_manifest["counts"]["normalized_timeline_entries"],
        )
        self.assertEqual(
            sum(source.source.record_count for source in session.sources),
            left_manifest["counts"]["input_records_total"],
        )

    def test_explicit_load_and_normalize_phases_match_public_inspection(self) -> None:
        scale = DATASET_SCALES["small"]
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            write_dataset(root, scale)
            paths = dataset_paths(root)
            evidence = _load_session_evidence(
                telemetry_path=paths.telemetry,
                link_events_path=paths.link_events,
                alarm_events_path=paths.alarm_events,
            )
            phased = _normalize_loaded_session(evidence)
            public = inspect_session(
                telemetry_path=paths.telemetry,
                link_events_path=paths.link_events,
                alarm_events_path=paths.alarm_events,
            )

        self.assertEqual(phased, public)

    def test_peak_rss_units_are_normalized_for_supported_hosts(self) -> None:
        self.assertEqual(normalize_peak_rss_bytes(123, "Linux"), 123 * 1024)
        self.assertEqual(normalize_peak_rss_bytes(123, "Darwin"), 123)
        self.assertIsNone(normalize_peak_rss_bytes(123, "Windows"))


class SessionBenchmarkCommandTests(unittest.TestCase):
    def run_command(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "scripts/session_inspection_benchmark.py", *arguments],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_bounded_smoke_sample_uses_fresh_worker(self) -> None:
        result = self.run_command("smoke")
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("session inspection benchmark smoke ok:", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_raw_benchmark_result_passes_internal_validator(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            output = Path(directory_name) / "benchmark.json"
            result = self.run_command(
                "benchmark",
                "--scales",
                "small",
                "--samples",
                "1",
                "--warmups",
                "0",
                "--output",
                str(output),
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            validate = self.run_command("validate", str(output))

        self.assertEqual(validate.returncode, 0, msg=validate.stderr or validate.stdout)
        self.assertIn("session inspection benchmark result valid:", validate.stdout)
        self.assertEqual(validate.stderr, "")


if __name__ == "__main__":
    unittest.main()

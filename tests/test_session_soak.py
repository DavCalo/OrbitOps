from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SessionSoakCommandTests(unittest.TestCase):
    def run_command(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "scripts/session_inspection_soak.py", *arguments],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_bounded_soak_smoke_uses_long_lived_runner_path(self) -> None:
        result = self.run_command("smoke")

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("session inspection soak smoke ok:", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_raw_soak_result_passes_internal_validator(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            output = Path(directory_name) / "soak.json"
            result = self.run_command(
                "run",
                "--scale",
                "small",
                "--duration-seconds",
                "0.05",
                "--iteration-interval-seconds",
                "0",
                "--resource-sample-interval-seconds",
                "0.01",
                "--output",
                str(output),
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(output.read_text(encoding="utf-8"))
            validate = self.run_command("validate", str(output))

        self.assertEqual(validate.returncode, 0, msg=validate.stderr or validate.stdout)
        self.assertIn("session inspection soak result valid:", validate.stdout)
        self.assertFalse(payload["summary"]["reference_soak_criteria_met"])
        self.assertGreaterEqual(len(payload["resource_samples"]), 2)
        self.assertEqual(payload["final_summary"]["source_count"], 3)
        self.assertEqual(validate.stderr, "")

    def test_soak_cli_rejects_nonfinite_duration_and_intervals(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            output = Path(directory_name) / "soak.json"
            cases = (
                ("--duration-seconds", "nan"),
                ("--duration-seconds", "inf"),
                ("--iteration-interval-seconds", "nan"),
                ("--iteration-interval-seconds", "inf"),
                ("--resource-sample-interval-seconds", "nan"),
                ("--resource-sample-interval-seconds", "inf"),
            )
            for option, value in cases:
                with self.subTest(option=option, value=value):
                    result = self.run_command(
                        "run",
                        "--duration-seconds",
                        "0",
                        option,
                        value,
                        "--output",
                        str(output),
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("must be finite", result.stderr)

    def test_soak_validator_rejects_nonfinite_numeric_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            output = Path(directory_name) / "soak.json"
            result = self.run_command(
                "run",
                "--scale",
                "small",
                "--duration-seconds",
                "0",
                "--iteration-interval-seconds",
                "0",
                "--resource-sample-interval-seconds",
                "1",
                "--output",
                str(output),
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(output.read_text(encoding="utf-8"))
            payload["parameters"]["duration_seconds_requested"] = float("nan")
            output.write_text(json.dumps(payload), encoding="utf-8")
            validate = self.run_command("validate", str(output))

        self.assertNotEqual(validate.returncode, 0)
        self.assertIn("must be finite", validate.stderr)

    def test_soak_validator_rejects_tampered_final_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            output = Path(directory_name) / "soak.json"
            result = self.run_command(
                "run",
                "--scale",
                "small",
                "--duration-seconds",
                "0",
                "--iteration-interval-seconds",
                "0",
                "--resource-sample-interval-seconds",
                "1",
                "--output",
                str(output),
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(output.read_text(encoding="utf-8"))
            payload["final_summary"]["timeline_entries_total"] += 1
            output.write_text(json.dumps(payload), encoding="utf-8")
            validate = self.run_command("validate", str(output))

        self.assertNotEqual(validate.returncode, 0)
        self.assertIn("does not match dataset", validate.stderr)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orbitops.alarm_policies import (
    alarm_policy_fingerprint,
    list_builtin_alarm_policies,
    load_builtin_alarm_policy,
)
from orbitops.alarms import DEFAULT_ALARM_POLICY
from orbitops.cli import main


class AlarmPolicyCliTests(unittest.TestCase):
    def test_list_prints_one_stable_builtin_name_per_line(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["alarm-policy", "list"]), 0)
        self.assertEqual(output.getvalue().splitlines(), list(list_builtin_alarm_policies()))

    def test_show_prints_stable_compact_json(self) -> None:
        policy = load_builtin_alarm_policy("standard")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["alarm-policy", "show", "standard"]), 0)

        expected = {
            "battery": {"critical_v": 7.0, "hysteresis_v": 0.0},
            "description": "Backward-compatible OrbitOps v0.3 alarm thresholds.",
            "fingerprint": alarm_policy_fingerprint(policy),
            "mode": {"alarm_on_safe": True},
            "name": "standard",
            "schema_version": 1,
            "sequence": {"detect_gaps": True},
            "temperature": {
                "critical_c": 60.0,
                "hysteresis_c": 0.0,
                "warning_c": 50.0,
            },
        }
        self.assertEqual(
            output.getvalue(),
            json.dumps(expected, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        )

    def test_validate_accepts_external_policy_and_prints_machine_readable_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "external.toml"
            standard = (
                Path(__file__).resolve().parents[1]
                / "ground_station/orbitops/alarm_policies/builtin/standard.toml"
            )
            path.write_text(
                standard.read_text(encoding="utf-8").replace(
                    'name = "standard"',
                    'name = "external"',
                ),
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["alarm-policy", "validate", str(path)]), 0)

        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "fingerprint": alarm_policy_fingerprint(DEFAULT_ALARM_POLICY),
                "name": "external",
                "valid": True,
            },
        )

    def test_show_and_validate_fail_with_actionable_context(self) -> None:
        for operation in ("show", "validate"):
            with (
                self.subTest(operation=operation),
                self.assertRaisesRegex(
                    SystemExit,
                    rf"alarm-policy {operation} failed: alarm policy reference 'missing'",
                ),
            ):
                main(["alarm-policy", operation, "missing"])

    def test_root_cli_delegates_alarm_policy_command(self) -> None:
        with patch("orbitops.cli.run_alarm_policy_command", return_value=9) as mocked:
            self.assertEqual(main(["alarm-policy", "list"]), 9)
        mocked.assert_called_once()
        call = mocked.call_args
        self.assertIsNotNone(call)
        assert call is not None
        args = call.args[0]
        self.assertEqual(args.command, "alarm-policy")
        self.assertEqual(args.alarm_policy_command, "list")

    def test_listen_without_selection_uses_backward_compatible_default(self) -> None:
        with patch("orbitops.cli.listen") as mocked:
            self.assertEqual(main(["listen"]), 0)
        mocked.assert_called_once_with("127.0.0.1", 9000, None, DEFAULT_ALARM_POLICY)

    def test_listen_resolves_selected_policy_before_delegating(self) -> None:
        policy = load_builtin_alarm_policy("thermal-demo")
        with patch("orbitops.cli.listen") as mocked:
            self.assertEqual(main(["listen", "--alarm-policy", "thermal-demo"]), 0)
        mocked.assert_called_once_with("127.0.0.1", 9000, None, policy)

    def test_invalid_policy_has_no_receiver_or_recording_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recording = Path(directory) / "capture.jsonl"
            with (
                patch("orbitops.cli.listen") as mocked,
                self.assertRaisesRegex(SystemExit, "listen failed: alarm policy reference"),
            ):
                main(
                    [
                        "listen",
                        "--alarm-policy",
                        "missing",
                        "--record",
                        str(recording),
                    ]
                )
            mocked.assert_not_called()
            self.assertFalse(recording.exists())


if __name__ == "__main__":
    unittest.main()

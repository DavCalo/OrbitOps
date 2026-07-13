from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops import __version__  # noqa: E402
from orbitops.alarms import DEFAULT_ALARM_POLICY  # noqa: E402
from orbitops.cli import main  # noqa: E402
from orbitops.protocol import Mode, TelemetryPacket, encode_packet  # noqa: E402


def encoded_packet() -> bytes:
    return encode_packet(
        TelemetryPacket(
            sequence=1,
            timestamp_ms=1,
            mode=Mode.NOMINAL,
            battery_mv=8100,
            bus_current_ma=400,
            temperature_centi_c=2500,
            roll_centi_deg=0,
            pitch_centi_deg=0,
            yaw_centi_deg=0,
        )
    )


class CliTests(unittest.TestCase):
    def test_version(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            main(["--version"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn(__version__, output.getvalue())

    def test_invalid_port(self) -> None:
        with self.assertRaisesRegex(SystemExit, "port must be"):
            main(["listen", "--port", "70000"])

    def test_listen_delegates_with_default_alarm_metadata(self) -> None:
        with patch("orbitops.cli.listen") as mocked:
            self.assertEqual(main(["listen", "--port", "9010"]), 0)
        mocked.assert_called_once_with(
            "127.0.0.1",
            9010,
            None,
            DEFAULT_ALARM_POLICY,
            None,
            "builtin:standard",
        )

    def test_listen_delegates_alarm_log_and_selected_policy_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            alarm_log = Path(directory) / "alarms.jsonl"
            with (
                patch(
                    "orbitops.cli.resolve_alarm_policy",
                    return_value=DEFAULT_ALARM_POLICY,
                ) as resolve,
                patch("orbitops.cli.listen") as mocked,
            ):
                self.assertEqual(
                    main(
                        [
                            "listen",
                            "--alarm-policy",
                            "file:policy.toml",
                            "--alarm-log",
                            str(alarm_log),
                        ]
                    ),
                    0,
                )

        resolve.assert_called_once_with("file:policy.toml")
        mocked.assert_called_once_with(
            "127.0.0.1",
            9000,
            None,
            DEFAULT_ALARM_POLICY,
            alarm_log,
            "file:policy.toml",
        )

    def test_invalid_alarm_policy_fails_before_receiver_delegation(self) -> None:
        with (
            patch(
                "orbitops.cli.resolve_alarm_policy",
                side_effect=ValueError("invalid policy"),
            ),
            patch("orbitops.cli.listen") as mocked,
            self.assertRaisesRegex(SystemExit, "listen failed"),
        ):
            main(
                [
                    "listen",
                    "--alarm-policy",
                    "missing",
                    "--alarm-log",
                    "alarms.jsonl",
                ]
            )
        mocked.assert_not_called()

    def test_profile_delegates_to_profile_cli(self) -> None:
        with patch("orbitops.cli.run_profile_command", return_value=7) as mocked:
            self.assertEqual(main(["profile", "list"]), 7)
        mocked.assert_called_once()
        call = mocked.call_args
        self.assertIsNotNone(call)
        assert call is not None
        args = call.args[0]
        self.assertEqual(args.command, "profile")
        self.assertEqual(args.profile_command, "list")

    def test_missing_replay_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.jsonl"
            with self.assertRaisesRegex(SystemExit, "session file not found"):
                main(["replay", str(missing)])

    def test_invalid_replay_speed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory) / "session.jsonl"
            session.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "speed must be positive"):
                main(["replay", str(session), "--speed", "0"])

    def test_replay_processes_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory) / "session.jsonl"
            session.write_text("placeholder", encoding="utf-8")
            with (
                patch("orbitops.cli.iter_records", return_value=[encoded_packet()]),
                patch("orbitops.cli.process_packet") as process,
            ):
                self.assertEqual(main(["replay", str(session)]), 0)
            process.assert_called_once()

    def test_decode_prints_packet(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["decode", encoded_packet().hex()]), 0)
        self.assertIn("'sequence': 1", output.getvalue())

    def test_decode_rejects_invalid_hex(self) -> None:
        with self.assertRaisesRegex(SystemExit, "decode failed"):
            main(["decode", "not-hex"])


if __name__ == "__main__":
    unittest.main()

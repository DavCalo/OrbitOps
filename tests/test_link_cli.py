from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from orbitops.cli import build_parser, main
from orbitops.link import LinkConfig, LinkStatistics


class LinkCliTests(unittest.TestCase):
    def test_defaults(self) -> None:
        args = build_parser().parse_args(["link"])

        self.assertEqual(args.listen_host, "127.0.0.1")
        self.assertEqual(args.listen_port, 9001)
        self.assertEqual(args.forward_host, "127.0.0.1")
        self.assertEqual(args.forward_port, 9000)
        self.assertEqual(args.seed, 0)
        self.assertEqual(args.loss_rate, 0.0)
        self.assertEqual(args.latency_ms, 0)
        self.assertIsNone(args.event_log)
        self.assertIsNone(args.session_id)
        self.assertIsNone(args.max_packets)

    def test_invalid_arguments_are_rejected_before_runtime_construction(self) -> None:
        invalid_commands = [
            ["link", "--listen-port", "0"],
            ["link", "--forward-port", "70000"],
            ["link", "--loss-rate", "-0.1"],
            ["link", "--duplicate-rate", "nan"],
            ["link", "--latency-ms", "-1"],
            ["link", "--reorder-window", "65536"],
            ["link", "--max-packets", "0"],
            ["link", "--session-id", "   "],
        ]

        for command in invalid_commands:
            with (
                self.subTest(command=command),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as raised,
                patch("orbitops.link.cli.LinkRuntime") as runtime_class,
            ):
                main(command)
            self.assertEqual(raised.exception.code, 2)
            runtime_class.assert_not_called()

    def test_command_builds_runtime_and_reports_statistics(self) -> None:
        runtime = Mock()
        runtime.bound_address = ("127.0.0.1", 9101)
        runtime.statistics = LinkStatistics(
            packets_received=3,
            packets_delayed=3,
            packets_duplicated=3,
            deliveries_scheduled=6,
            deliveries_forwarded=6,
        )
        token = Mock()
        token.hex = "generated-session"
        output = io.StringIO()

        with (
            patch("orbitops.link.cli.LinkRuntime", return_value=runtime) as runtime_class,
            patch("orbitops.link.cli.uuid.uuid4", return_value=token),
            contextlib.redirect_stdout(output),
        ):
            result = main(
                [
                    "link",
                    "--listen-port",
                    "9101",
                    "--forward-port",
                    "9100",
                    "--seed",
                    "42",
                    "--latency-ms",
                    "10",
                    "--duplicate-rate",
                    "1",
                    "--max-packets",
                    "3",
                ]
            )

        self.assertEqual(result, 0)
        runtime_class.assert_called_once_with(
            ("127.0.0.1", 9101),
            ("127.0.0.1", 9100),
            LinkConfig(seed=42, latency_ms=10, duplicate_rate=1.0),
            event_sink=None,
            session_id="generated-session",
        )
        runtime.open.assert_called_once_with()
        runtime.run.assert_called_once_with(max_packets=3)
        runtime.close.assert_called_once_with()
        self.assertIn("link ready: 127.0.0.1:9101", output.getvalue())
        self.assertIn("received=3", output.getvalue())
        self.assertIn("forwarded=6", output.getvalue())

    def test_event_log_is_created_and_explicit_session_is_used(self) -> None:
        runtime = Mock()
        runtime.bound_address = ("127.0.0.1", 9001)
        runtime.statistics = LinkStatistics()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            with (
                patch("orbitops.link.cli.LinkRuntime", return_value=runtime) as runtime_class,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(
                    main(
                        [
                            "link",
                            "--event-log",
                            str(path),
                            "--session-id",
                            "test-session",
                            "--max-packets",
                            "1",
                        ]
                    ),
                    0,
                )

            self.assertTrue(path.is_file())
            call = runtime_class.call_args
            self.assertIsNotNone(call)
            assert call is not None
            self.assertTrue(callable(call.kwargs["event_sink"]))
            self.assertEqual(call.kwargs["session_id"], "test-session")

    def test_runtime_error_becomes_actionable_cli_failure(self) -> None:
        runtime = Mock()
        runtime.open.side_effect = OSError("address already in use")

        with (
            patch("orbitops.link.cli.LinkRuntime", return_value=runtime),
            self.assertRaisesRegex(SystemExit, "link failed: address already in use"),
        ):
            main(["link"])


if __name__ == "__main__":
    unittest.main()

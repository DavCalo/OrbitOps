from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from orbitops.cli import build_parser, main
from orbitops.link import (
    LinkConfig,
    LinkRunMetadata,
    LinkStatistics,
    configuration_fingerprint,
)


class LinkCliTests(unittest.TestCase):
    def test_defaults(self) -> None:
        args = build_parser().parse_args(["link"])

        self.assertEqual(args.listen_host, "127.0.0.1")
        self.assertEqual(args.listen_port, 9001)
        self.assertEqual(args.forward_host, "127.0.0.1")
        self.assertEqual(args.forward_port, 9000)
        self.assertIsNone(args.profile)
        self.assertIsNone(args.seed)
        self.assertIsNone(args.loss_rate)
        self.assertIsNone(args.duplicate_rate)
        self.assertIsNone(args.corrupt_rate)
        self.assertIsNone(args.latency_ms)
        self.assertIsNone(args.jitter_ms)
        self.assertIsNone(args.reorder_window)
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
            ["link", "--profile", "   "],
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

    def test_command_builds_runtime_and_reports_configuration_identity(self) -> None:
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
        config = LinkConfig(seed=42, latency_ms=10, duplicate_rate=1.0)
        metadata = LinkRunMetadata(configuration_fingerprint(config))

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
            config,
            event_sink=None,
            session_id="generated-session",
            run_metadata=metadata,
        )
        runtime.open.assert_called_once_with()
        runtime.run.assert_called_once_with(max_packets=3)
        runtime.close.assert_called_once_with()
        ready = output.getvalue()
        self.assertIn("link ready: 127.0.0.1:9101", ready)
        self.assertIn("profile=none", ready)
        self.assertIn(f"config={metadata.configuration_fingerprint}", ready)
        self.assertIn("received=3", ready)
        self.assertIn("forwarded=6", ready)

    def test_omitted_cli_values_preserve_profile_and_metadata(self) -> None:
        runtime = Mock()
        runtime.bound_address = ("127.0.0.1", 9001)
        runtime.statistics = LinkStatistics()
        config = LinkConfig(
            seed=202603,
            loss_rate=0.15,
            latency_ms=80,
            jitter_ms=20,
            reorder_window=1,
        )

        with (
            patch("orbitops.link.cli.LinkRuntime", return_value=runtime) as runtime_class,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                main(["link", "--profile", "intermittent-loss", "--max-packets", "1"]),
                0,
            )

        call = runtime_class.call_args
        self.assertIsNotNone(call)
        assert call is not None
        self.assertEqual(call.args[2], config)
        self.assertEqual(
            call.kwargs["run_metadata"],
            LinkRunMetadata(
                configuration_fingerprint(config),
                profile_name="intermittent-loss",
                profile_reference="intermittent-loss",
                profile_schema_version=1,
            ),
        )

    def test_explicit_cli_values_override_profile_and_fingerprint(self) -> None:
        runtime = Mock()
        runtime.bound_address = ("127.0.0.1", 9001)
        runtime.statistics = LinkStatistics()
        config = LinkConfig(seed=7)

        with (
            patch("orbitops.link.cli.LinkRuntime", return_value=runtime) as runtime_class,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                main(
                    [
                        "link",
                        "--profile",
                        "intermittent-loss",
                        "--seed",
                        "7",
                        "--loss-rate",
                        "0",
                        "--latency-ms",
                        "0",
                        "--jitter-ms",
                        "0",
                        "--reorder-window",
                        "0",
                        "--max-packets",
                        "1",
                    ]
                ),
                0,
            )

        call = runtime_class.call_args
        self.assertIsNotNone(call)
        assert call is not None
        self.assertEqual(call.args[2], config)
        metadata = call.kwargs["run_metadata"]
        self.assertEqual(metadata.configuration_fingerprint, configuration_fingerprint(config))
        self.assertEqual(metadata.profile_name, "intermittent-loss")

    def test_invalid_profile_fails_before_runtime_or_event_log_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            event_log = Path(directory) / "events.jsonl"
            with (
                patch("orbitops.link.cli.LinkRuntime") as runtime_class,
                self.assertRaisesRegex(SystemExit, "link failed: mission profile reference"),
            ):
                main(
                    [
                        "link",
                        "--profile",
                        "missing",
                        "--event-log",
                        str(event_log),
                    ]
                )

            runtime_class.assert_not_called()
            self.assertFalse(event_log.exists())

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
            self.assertEqual(
                call.kwargs["run_metadata"],
                LinkRunMetadata(configuration_fingerprint(LinkConfig())),
            )

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

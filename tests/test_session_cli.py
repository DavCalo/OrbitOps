from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

from orbitops.cli import main
from orbitops.session import EvidenceLane, MalformedEvidenceError, NormalizedSession
from orbitops.session.cli import SessionExitCode
from orbitops.session.reporting import SessionReport


class SessionCliTests(unittest.TestCase):
    def run_report(
        self,
        *,
        complete: bool,
        compatible: bool,
        report_format: str = "text",
    ) -> tuple[int, str, Mock, Mock]:
        session = Mock(spec=NormalizedSession)
        session.is_complete = complete
        session.is_compatible = compatible
        report = cast(SessionReport, Mock(spec=SessionReport))
        output = io.StringIO()
        arguments = [
            "session",
            "inspect",
            "--telemetry",
            "telemetry.jsonl",
            "--format",
            report_format,
        ]
        with (
            patch("orbitops.session.cli.inspect_session", return_value=session) as inspect,
            patch(
                "orbitops.session.cli.project_session_report",
                return_value=report,
            ) as project,
            patch(
                "orbitops.session.cli.render_session_report_text",
                return_value="text-report\n",
            ),
            patch(
                "orbitops.session.cli.render_session_report_json",
                return_value='{"report":true}\n',
            ),
            contextlib.redirect_stdout(output),
        ):
            code = main(arguments)
        return code, output.getvalue(), inspect, project

    def test_complete_text_report_uses_exit_zero(self) -> None:
        code, output, inspect, project = self.run_report(complete=True, compatible=True)

        self.assertEqual(code, SessionExitCode.COMPLETE)
        self.assertEqual(output, "text-report\n")
        inspect.assert_called_once_with(
            telemetry_path=Path("telemetry.jsonl"),
            link_events_path=None,
            alarm_events_path=None,
        )
        project.assert_called_once_with(
            inspect.return_value,
            packet_sequence_min=None,
            packet_sequence_max=None,
            alarm_code=None,
            alarm_severity=None,
            event_limit=None,
        )

    def test_json_report_uses_the_json_renderer(self) -> None:
        code, output, _, _ = self.run_report(
            complete=True,
            compatible=True,
            report_format="json",
        )

        self.assertEqual(code, SessionExitCode.COMPLETE)
        self.assertEqual(output, '{"report":true}\n')

    def test_incomplete_session_uses_exit_one(self) -> None:
        code, _, _, _ = self.run_report(complete=False, compatible=True)
        self.assertEqual(code, SessionExitCode.INCOMPLETE)

    def test_incompatible_session_takes_precedence_over_incomplete(self) -> None:
        code, _, _, _ = self.run_report(complete=False, compatible=False)
        self.assertEqual(code, SessionExitCode.INCOMPATIBLE)

    def test_missing_evidence_is_an_argparse_usage_error(self) -> None:
        error = io.StringIO()
        with contextlib.redirect_stderr(error), self.assertRaises(SystemExit) as raised:
            main(["session", "inspect"])

        self.assertEqual(raised.exception.code, SessionExitCode.USAGE)
        self.assertIn("at least one of --telemetry", error.getvalue())

    def test_filters_are_forwarded_to_the_report_projection(self) -> None:
        session = Mock(spec=NormalizedSession)
        session.is_complete = True
        session.is_compatible = True
        report = cast(SessionReport, Mock(spec=SessionReport))
        with (
            patch("orbitops.session.cli.inspect_session", return_value=session),
            patch(
                "orbitops.session.cli.project_session_report",
                return_value=report,
            ) as project,
            patch(
                "orbitops.session.cli.render_session_report_text",
                return_value="report\n",
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            code = main(
                [
                    "session",
                    "inspect",
                    "--telemetry",
                    "telemetry.jsonl",
                    "--sequence-min",
                    "10",
                    "--sequence-max",
                    "20",
                    "--alarm-code",
                    "TEMP_HIGH",
                    "--alarm-severity",
                    "warning",
                    "--limit",
                    "5",
                ]
            )

        self.assertEqual(code, SessionExitCode.COMPLETE)
        project.assert_called_once_with(
            session,
            packet_sequence_min=10,
            packet_sequence_max=20,
            alarm_code="TEMP_HIGH",
            alarm_severity="warning",
            event_limit=5,
        )

    def test_invalid_sequence_range_is_a_usage_error_before_loading(self) -> None:
        error = io.StringIO()
        with (
            patch("orbitops.session.cli.inspect_session") as inspect,
            contextlib.redirect_stderr(error),
            self.assertRaises(SystemExit) as raised,
        ):
            main(
                [
                    "session",
                    "inspect",
                    "--telemetry",
                    "telemetry.jsonl",
                    "--sequence-min",
                    "20",
                    "--sequence-max",
                    "10",
                ]
            )

        self.assertEqual(raised.exception.code, SessionExitCode.USAGE)
        self.assertIn("must not exceed", error.getvalue())
        inspect.assert_not_called()

    def test_output_is_atomically_written_without_stdout(self) -> None:
        session = Mock(spec=NormalizedSession)
        session.is_complete = True
        session.is_compatible = True
        report = cast(SessionReport, Mock(spec=SessionReport))
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "report.json"
            stdout = io.StringIO()
            with (
                patch("orbitops.session.cli.inspect_session", return_value=session),
                patch(
                    "orbitops.session.cli.project_session_report",
                    return_value=report,
                ),
                patch(
                    "orbitops.session.cli.render_session_report_json",
                    return_value='{"report":true}\n',
                ),
                contextlib.redirect_stdout(stdout),
            ):
                code = main(
                    [
                        "session",
                        "inspect",
                        "--telemetry",
                        "telemetry.jsonl",
                        "--format",
                        "json",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(code, SessionExitCode.COMPLETE)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(output_path.read_text(encoding="utf-8"), '{"report":true}\n')
            self.assertEqual(list(output_path.parent.glob(".report.json.*.tmp")), [])

    def test_atomic_output_failure_preserves_existing_file_and_cleans_temp(self) -> None:
        session = Mock(spec=NormalizedSession)
        session.is_complete = True
        session.is_compatible = True
        report = cast(SessionReport, Mock(spec=SessionReport))
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "report.txt"
            output_path.write_text("previous report\n", encoding="utf-8")
            error = io.StringIO()
            with (
                patch("orbitops.session.cli.inspect_session", return_value=session),
                patch(
                    "orbitops.session.cli.project_session_report",
                    return_value=report,
                ),
                patch(
                    "orbitops.session.cli.render_session_report_text",
                    return_value="new report\n",
                ),
                patch(
                    "orbitops.session.cli.os.replace",
                    side_effect=PermissionError("replace denied"),
                ),
                contextlib.redirect_stderr(error),
            ):
                code = main(
                    [
                        "session",
                        "inspect",
                        "--telemetry",
                        "telemetry.jsonl",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(code, SessionExitCode.IO_ERROR)
            self.assertIn("replace denied", error.getvalue())
            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                "previous report\n",
            )
            self.assertEqual(list(output_path.parent.glob(".report.txt.*.tmp")), [])

    def test_malformed_evidence_uses_exit_four(self) -> None:
        error = io.StringIO()
        failure = MalformedEvidenceError(
            "invalid telemetry evidence",
            lane=EvidenceLane.TELEMETRY,
            source_name="telemetry.jsonl",
        )
        with (
            patch("orbitops.session.cli.inspect_session", side_effect=failure),
            contextlib.redirect_stderr(error),
        ):
            code = main(["session", "inspect", "--telemetry", "telemetry.jsonl"])

        self.assertEqual(code, SessionExitCode.MALFORMED)
        self.assertIn("invalid telemetry evidence", error.getvalue())

    def test_filesystem_failure_uses_exit_five(self) -> None:
        error = io.StringIO()
        failure = FileNotFoundError(2, "No such file", "telemetry.jsonl")
        with (
            patch("orbitops.session.cli.inspect_session", side_effect=failure),
            contextlib.redirect_stderr(error),
        ):
            code = main(["session", "inspect", "--telemetry", "telemetry.jsonl"])

        self.assertEqual(code, SessionExitCode.IO_ERROR)
        self.assertIn("telemetry.jsonl", error.getvalue())


if __name__ == "__main__":
    unittest.main()

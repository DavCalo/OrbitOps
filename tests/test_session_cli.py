from __future__ import annotations

import contextlib
import io
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
    ) -> tuple[int, str, Mock]:
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
            patch.object(SessionReport, "from_session", return_value=report),
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
        return code, output.getvalue(), inspect

    def test_complete_text_report_uses_exit_zero(self) -> None:
        code, output, inspect = self.run_report(complete=True, compatible=True)

        self.assertEqual(code, SessionExitCode.COMPLETE)
        self.assertEqual(output, "text-report\n")
        inspect.assert_called_once_with(
            telemetry_path=Path("telemetry.jsonl"),
            link_events_path=None,
            alarm_events_path=None,
        )

    def test_json_report_uses_the_json_renderer(self) -> None:
        code, output, _ = self.run_report(
            complete=True,
            compatible=True,
            report_format="json",
        )

        self.assertEqual(code, SessionExitCode.COMPLETE)
        self.assertEqual(output, '{"report":true}\n')

    def test_incomplete_session_uses_exit_one(self) -> None:
        code, _, _ = self.run_report(complete=False, compatible=True)
        self.assertEqual(code, SessionExitCode.INCOMPLETE)

    def test_incompatible_session_takes_precedence_over_incomplete(self) -> None:
        code, _, _ = self.run_report(complete=False, compatible=False)
        self.assertEqual(code, SessionExitCode.INCOMPATIBLE)

    def test_missing_evidence_is_an_argparse_usage_error(self) -> None:
        error = io.StringIO()
        with contextlib.redirect_stderr(error), self.assertRaises(SystemExit) as raised:
            main(["session", "inspect"])

        self.assertEqual(raised.exception.code, SessionExitCode.USAGE)
        self.assertIn("at least one of --telemetry", error.getvalue())

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

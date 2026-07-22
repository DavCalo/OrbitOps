"""Public command-line adapter for deterministic session inspection reports."""

from __future__ import annotations

import argparse
import sys
from enum import IntEnum
from pathlib import Path
from typing import cast

from .errors import MalformedEvidenceError
from .inspection import inspect_session
from .reporting import SessionReport, render_session_report_json, render_session_report_text


class SessionExitCode(IntEnum):
    """Stable process exit codes for ``orbitops session inspect``."""

    COMPLETE = 0
    INCOMPLETE = 1
    USAGE = 2
    INCOMPATIBLE = 3
    MALFORMED = 4
    IO_ERROR = 5


def configure_session_parser(parser: argparse.ArgumentParser) -> None:
    """Add public session-inspection subcommands and stable options."""

    subparsers = parser.add_subparsers(dest="session_command", required=True)
    inspect_parser = subparsers.add_parser(
        "inspect",
        help="inspect selected telemetry, link, and alarm evidence",
        description=(
            "Load one or more OrbitOps evidence sources and print a deterministic "
            "normalized session report."
        ),
    )
    inspect_parser.add_argument(
        "--telemetry",
        type=Path,
        metavar="PATH",
        help="telemetry recording JSONL",
    )
    inspect_parser.add_argument(
        "--link-events",
        type=Path,
        metavar="PATH",
        help="link-event JSONL",
    )
    inspect_parser.add_argument(
        "--alarm-events",
        type=Path,
        metavar="PATH",
        help="alarm-event JSONL",
    )
    inspect_parser.add_argument(
        "--format",
        dest="report_format",
        choices=("text", "json"),
        default="text",
        help="report representation (default: text)",
    )
    inspect_parser.set_defaults(_session_inspect_parser=inspect_parser)


def _write_failure(message: str) -> None:
    sys.stderr.write(f"session inspect failed: {message}\n")


def _exit_code(*, complete: bool, compatible: bool) -> SessionExitCode:
    if not compatible:
        return SessionExitCode.INCOMPATIBLE
    if not complete:
        return SessionExitCode.INCOMPLETE
    return SessionExitCode.COMPLETE


def run_session_command(args: argparse.Namespace) -> int:
    """Run one public session-inspection CLI operation."""

    command: str = args.session_command
    if command != "inspect":
        raise AssertionError(f"unhandled session command: {command}")

    telemetry_path: Path | None = args.telemetry
    link_events_path: Path | None = args.link_events
    alarm_events_path: Path | None = args.alarm_events
    if telemetry_path is None and link_events_path is None and alarm_events_path is None:
        parser = cast(argparse.ArgumentParser, args._session_inspect_parser)
        parser.error("at least one of --telemetry, --link-events, or --alarm-events is required")

    try:
        session = inspect_session(
            telemetry_path=telemetry_path,
            link_events_path=link_events_path,
            alarm_events_path=alarm_events_path,
        )
    except MalformedEvidenceError as exc:
        _write_failure(str(exc))
        return int(SessionExitCode.MALFORMED)
    except OSError as exc:
        _write_failure(str(exc))
        return int(SessionExitCode.IO_ERROR)

    report = SessionReport.from_session(session)
    report_format: str = args.report_format
    rendered = (
        render_session_report_json(report)
        if report_format == "json"
        else render_session_report_text(report)
    )
    try:
        sys.stdout.write(rendered)
    except OSError as exc:
        _write_failure(str(exc))
        return int(SessionExitCode.IO_ERROR)

    return int(_exit_code(complete=session.is_complete, compatible=session.is_compatible))

"""Public command-line adapter for deterministic session inspection reports."""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import tempfile
from enum import IntEnum
from pathlib import Path
from typing import cast

from .errors import MalformedEvidenceError
from .inspection import inspect_session
from .reporting import (
    ALARM_SEVERITY_CHOICES,
    MAX_REPORT_EVENTS,
    project_session_report,
    render_session_report_json,
    render_session_report_text,
)


class SessionExitCode(IntEnum):
    """Stable process exit codes for ``orbitops session inspect``."""

    COMPLETE = 0
    INCOMPLETE = 1
    USAGE = 2
    INCOMPATIBLE = 3
    MALFORMED = 4
    IO_ERROR = 5


def _packet_sequence_argument(value: str) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a base-10 integer") from exc
    if not 0 <= parsed <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError("must fit an unsigned 32-bit integer")
    return parsed


def _event_limit_argument(value: str) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a base-10 integer") from exc
    if not 1 <= parsed <= MAX_REPORT_EVENTS:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_REPORT_EVENTS}")
    return parsed


def _alarm_code_argument(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise argparse.ArgumentTypeError("must be non-empty")
    if "\x00" in normalized:
        raise argparse.ArgumentTypeError("must not contain NUL characters")
    return normalized


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
    inspect_parser.add_argument(
        "--sequence-min",
        type=_packet_sequence_argument,
        metavar="N",
        help="retain entries with packet_sequence greater than or equal to N",
    )
    inspect_parser.add_argument(
        "--sequence-max",
        type=_packet_sequence_argument,
        metavar="N",
        help="retain entries with packet_sequence less than or equal to N",
    )
    inspect_parser.add_argument(
        "--alarm-code",
        type=_alarm_code_argument,
        metavar="CODE",
        help="retain alarm transitions with this exact normalized code",
    )
    inspect_parser.add_argument(
        "--alarm-severity",
        choices=ALARM_SEVERITY_CHOICES,
        metavar="SEVERITY",
        help="retain alarm transitions with this severity",
    )
    inspect_parser.add_argument(
        "--limit",
        dest="event_limit",
        type=_event_limit_argument,
        metavar="N",
        help=f"render at most N matching timeline entries (maximum: {MAX_REPORT_EVENTS})",
    )
    inspect_parser.add_argument(
        "--output",
        type=Path,
        metavar="PATH",
        help="atomically write the report to PATH instead of stdout",
    )
    inspect_parser.set_defaults(_session_inspect_parser=inspect_parser)


def _write_failure(message: str) -> None:
    sys.stderr.write(f"session inspect failed: {message}\n")


def _write_report_atomically(output_path: Path, rendered: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        if temporary_path is None:
            raise AssertionError("temporary report path was not created")
        os.replace(temporary_path, output_path)
    except OSError:
        if temporary_path is not None:
            with contextlib.suppress(OSError):
                temporary_path.unlink(missing_ok=True)
        raise


def _write_report(rendered: str, output_path: Path | None) -> None:
    if output_path is None:
        sys.stdout.write(rendered)
        return
    _write_report_atomically(output_path, rendered)


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

    packet_sequence_min: int | None = args.sequence_min
    packet_sequence_max: int | None = args.sequence_max
    if (
        packet_sequence_min is not None
        and packet_sequence_max is not None
        and packet_sequence_min > packet_sequence_max
    ):
        parser = cast(argparse.ArgumentParser, args._session_inspect_parser)
        parser.error("--sequence-min must not exceed --sequence-max")

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

    report = project_session_report(
        session,
        packet_sequence_min=packet_sequence_min,
        packet_sequence_max=packet_sequence_max,
        alarm_code=args.alarm_code,
        alarm_severity=args.alarm_severity,
        event_limit=args.event_limit,
    )
    report_format: str = args.report_format
    rendered = (
        render_session_report_json(report)
        if report_format == "json"
        else render_session_report_text(report)
    )
    output_path: Path | None = args.output
    try:
        _write_report(rendered, output_path)
    except OSError as exc:
        _write_failure(str(exc))
        return int(SessionExitCode.IO_ERROR)

    return int(_exit_code(complete=session.is_complete, compatible=session.is_compatible))

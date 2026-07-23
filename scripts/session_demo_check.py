#!/usr/bin/env python3
"""Exercise the installed OrbitOps CLI through one complete inspected session."""

from __future__ import annotations

import json
import os
import selectors
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import cast

from orbitops import __version__
from orbitops.alarm_events import (
    AlarmEvent,
    AlarmEventType,
    load_alarm_events,
)
from orbitops.alarm_events import (
    run_metadata_from_events as alarm_metadata_from_events,
)
from orbitops.alarm_events import (
    validate_run_summary as validate_alarm_summary,
)
from orbitops.alarm_policies import alarm_policy_fingerprint, load_builtin_alarm_policy
from orbitops.link import (
    configuration_fingerprint,
    load_link_events,
)
from orbitops.link import (
    run_metadata_from_events as link_metadata_from_events,
)
from orbitops.link import (
    validate_run_summary as validate_link_summary,
)
from orbitops.profiles import load_builtin_profile
from orbitops.recorder import load_telemetry_records
from orbitops.session import REPORT_FORMAT, REPORT_FORMAT_VERSION, SessionReportDocument

_ROOT = Path(__file__).resolve().parents[1]
_PACKET_COUNT = 52
_PROFILE_NAME = "intermittent-loss"
_POLICY_NAME = "thermal-demo"
_SESSION_ID = "session-inspection-demo"
_TEXT_EVENT_LIMIT = 16
_EXPECTED_TELEMETRY_GAPS = 6
_EXPECTED_ALARM_CODES = frozenset(
    {
        "ELEVATED_TEMPERATURE",
        "HIGH_TEMPERATURE",
        "SAFE_MODE",
        "SEQUENCE_GAP",
    }
)
_EXPECTED_ALARM_COUNTS = {
    "transitions_raised": 8,
    "transitions_updated": 1,
    "transitions_cleared": 0,
    "transitions_total": 9,
}
_EXPECTED_LINK_COUNTS = {
    "packets_received": 52,
    "packets_dropped": 7,
    "packets_delayed": 45,
    "packets_duplicated": 0,
    "packets_corrupted": 0,
    "packets_reordered": 0,
    "deliveries_scheduled": 45,
    "deliveries_forwarded": 45,
}


def _installed_cli() -> str:
    executable = shutil.which("orbitops")
    if executable is None:
        raise RuntimeError("installed orbitops CLI not found on PATH")
    return executable


def _reserve_udp_ports() -> tuple[int, int]:
    with (
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as first,
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as second,
    ):
        first.bind(("127.0.0.1", 0))
        second.bind(("127.0.0.1", 0))
        return int(first.getsockname()[1]), int(second.getsockname()[1])


def _wait_for_line(
    process: subprocess.Popen[str],
    *,
    prefix: str,
    description: str,
) -> str:
    if process.stdout is None:
        raise RuntimeError(f"{description} stdout is unavailable")

    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout=5.0):
            raise RuntimeError(f"{description} did not report readiness")
        line = process.stdout.readline().strip()
    finally:
        selector.close()

    if not line.startswith(prefix):
        raise RuntimeError(f"unexpected {description} output: {line!r}")
    return line


def _wait_until(
    process: subprocess.Popen[str],
    predicate: Callable[[], bool],
    *,
    description: str,
) -> None:
    deadline = time.monotonic() + 10.0
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"{description} failed because the process exited: returncode={process.returncode}"
            )
        try:
            if predicate():
                return
        except (OSError, ValueError) as exc:
            last_error = exc
        time.sleep(0.02)

    detail = "" if last_error is None else f": last error={last_error}"
    raise RuntimeError(f"timed out waiting for {description}{detail}")


def _alarm_codes(events: Sequence[AlarmEvent]) -> frozenset[str]:
    codes: set[str] = set()
    for event in events:
        if event.event_type not in {
            AlarmEventType.ALARM_RAISED,
            AlarmEventType.ALARM_UPDATED,
            AlarmEventType.ALARM_CLEARED,
        }:
            continue
        code = event.attributes.get("code")
        if isinstance(code, str):
            codes.add(code)
    return frozenset(codes)


def _interrupt_and_collect(process: subprocess.Popen[str]) -> tuple[str, str]:
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
    try:
        return process.communicate(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            return process.communicate(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.communicate(timeout=2.0)


def _terminate(process: subprocess.Popen[str], *, interrupt: bool = False) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGINT) if interrupt else process.terminate()
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2.0)


def _run(command: Sequence[str], *, timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "command failed: "
            f"returncode={result.returncode} command={list(command)!r} "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    return result


def _parse_report(text: str) -> SessionReportDocument:
    document: object = json.loads(text)
    if not isinstance(document, dict):
        raise RuntimeError("session inspector did not emit a JSON object")
    return cast(SessionReportDocument, document)


def _validate_report(
    document: SessionReportDocument,
    *,
    telemetry_count: int,
    alarm_counters: Mapping[str, int],
    link_counters: Mapping[str, int],
    policy_fingerprint: str,
    profile_fingerprint: str,
) -> None:
    metadata = document["metadata"]
    if (
        metadata["report_format"] != REPORT_FORMAT
        or metadata["report_format_version"] != REPORT_FORMAT_VERSION
        or metadata["cross_stream_provenance_verified"]
    ):
        raise RuntimeError(f"unexpected report metadata: {metadata}")

    summary = document["summary"]
    if not summary["complete"] or not summary["compatible"]:
        raise RuntimeError(f"session report is not complete and compatible: {summary}")

    sources = document["sources"]
    if [source["lane"] for source in sources] != ["telemetry", "alarm", "link"]:
        raise RuntimeError(f"unexpected source ordering: {sources}")
    by_lane = {source["lane"]: source for source in sources}

    telemetry = by_lane["telemetry"]
    telemetry_counters = telemetry["counters"]
    if (
        telemetry["completeness"] != "unknown"
        or telemetry_counters["records_total"] != telemetry_count
        or telemetry_counters["packets_decoded"] != telemetry_count
        or telemetry_counters["packets_rejected"] != 0
        or telemetry_counters["sequence_gaps"] != _EXPECTED_TELEMETRY_GAPS
        or telemetry_counters["sequence_duplicates"] != 0
    ):
        raise RuntimeError(f"unexpected telemetry source: {telemetry}")

    alarm = by_lane["alarm"]
    if (
        alarm["completeness"] != "complete"
        or not alarm["summary_present"]
        or alarm["counters"] != dict(alarm_counters)
        or alarm["metadata"].get("policy_name") != _POLICY_NAME
        or alarm["metadata"].get("policy_fingerprint") != policy_fingerprint
    ):
        raise RuntimeError(f"unexpected alarm source: {alarm}")

    link = by_lane["link"]
    if (
        link["completeness"] != "complete"
        or not link["summary_present"]
        or link["session_id"] != _SESSION_ID
        or link["counters"] != dict(link_counters)
        or link["metadata"].get("profile_name") != _PROFILE_NAME
        or link["metadata"].get("configuration_fingerprint") != profile_fingerprint
    ):
        raise RuntimeError(f"unexpected link source: {link}")

    timeline = document["timeline"]
    if len(timeline) != summary["timeline_entries_total"] or summary[
        "timeline_entries_rendered"
    ] != len(timeline):
        raise RuntimeError(f"unfiltered timeline counters are inconsistent: {summary}")

    for lane in ("telemetry", "alarm", "link"):
        indices = [entry["source_index"] for entry in timeline if entry["lane"] == lane]
        if indices != sorted(indices):
            raise RuntimeError(f"{lane} timeline order is not source-local: {indices}")

    alarm_entries = [entry for entry in timeline if entry["lane"] == "alarm"]
    if not alarm_entries:
        raise RuntimeError("report contains no alarm transitions")
    for entry in alarm_entries:
        correlation = entry["correlation"]
        if (
            correlation is None
            or correlation["kind"] != "exact"
            or len(correlation["candidate_record_indices"]) != 1
        ):
            raise RuntimeError(f"alarm transition is not exactly correlated: {entry}")

    link_entries = [entry for entry in timeline if entry["lane"] == "link"]
    if not link_entries:
        raise RuntimeError("report contains no distinct link-event lane")
    if any(
        entry["packet_sequence"] is not None or entry["correlation"] is not None
        for entry in link_entries
    ):
        raise RuntimeError("link lane incorrectly claims telemetry correlation")

    diagnostic_codes = {item["code"] for item in document["diagnostics"]}
    if "telemetry_sequence_gap" not in diagnostic_codes:
        raise RuntimeError("demo did not expose a telemetry sequence-gap diagnostic")
    if diagnostic_codes & {
        "alarm_correlation_ambiguous",
        "alarm_correlation_impossible",
    }:
        raise RuntimeError(f"unexpected alarm correlation diagnostics: {diagnostic_codes}")


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} PATH_TO_SIMULATOR", file=sys.stderr)
        return 2

    simulator = Path(sys.argv[1]).resolve()
    if not simulator.is_file():
        print(f"simulator not found: {simulator}", file=sys.stderr)
        return 2

    executable = _installed_cli()
    profile = load_builtin_profile(_PROFILE_NAME)
    policy = load_builtin_alarm_policy(_POLICY_NAME)
    effective_link_config = replace(
        profile.link_config,
        jitter_ms=0,
        reorder_window=0,
    )
    profile_fingerprint = configuration_fingerprint(effective_link_config)
    policy_fingerprint = alarm_policy_fingerprint(policy)
    listener_port, link_port = _reserve_udp_ports()

    with tempfile.TemporaryDirectory(prefix="orbitops-session-demo-") as directory_name:
        directory = Path(directory_name)
        telemetry_path = directory / "telemetry.jsonl"
        link_path = directory / "link-events.jsonl"
        alarm_path = directory / "alarm-events.jsonl"

        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        listener = subprocess.Popen(
            [
                executable,
                "listen",
                "--host",
                "127.0.0.1",
                "--port",
                str(listener_port),
                "--record",
                str(telemetry_path),
                "--alarm-policy",
                _POLICY_NAME,
                "--alarm-log",
                str(alarm_path),
            ],
            cwd=_ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        link_process: subprocess.Popen[str] | None = None
        try:
            listener_ready = _wait_for_line(
                listener,
                prefix="OrbitOps ground station listening on udp://",
                description="installed listener",
            )
            _wait_until(
                listener,
                lambda: (
                    alarm_path.is_file()
                    and alarm_metadata_from_events(load_alarm_events(alarm_path)) is not None
                ),
                description="alarm run metadata",
            )

            link_process = subprocess.Popen(
                [
                    executable,
                    "link",
                    "--profile",
                    _PROFILE_NAME,
                    "--jitter-ms",
                    "0",
                    "--reorder-window",
                    "0",
                    "--listen-host",
                    "127.0.0.1",
                    "--listen-port",
                    str(link_port),
                    "--forward-host",
                    "127.0.0.1",
                    "--forward-port",
                    str(listener_port),
                    "--event-log",
                    str(link_path),
                    "--session-id",
                    _SESSION_ID,
                    "--max-packets",
                    str(_PACKET_COUNT),
                ],
                cwd=_ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            link_ready = _wait_for_line(
                link_process,
                prefix="link ready:",
                description="installed link CLI",
            )

            simulator_run = _run(
                [
                    str(simulator),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(link_port),
                    "--packets",
                    str(_PACKET_COUNT),
                    "--interval-ms",
                    "5",
                    "--scenario",
                    "thermal",
                ]
            )
            link_stdout, link_stderr = link_process.communicate(timeout=20.0)
            if link_process.returncode != 0 or link_stderr.strip():
                raise RuntimeError(
                    "installed link CLI failed: "
                    f"returncode={link_process.returncode} "
                    f"stdout={link_stdout.strip()!r} stderr={link_stderr.strip()!r}"
                )

            link_events = load_link_events(link_path)
            link_statistics = validate_link_summary(link_events)
            link_counters = link_statistics.to_dict()
            for name, expected in _EXPECTED_LINK_COUNTS.items():
                if link_counters[name] != expected:
                    raise RuntimeError(
                        f"unexpected deterministic link counter {name}: "
                        f"expected={expected} actual={link_counters[name]}"
                    )
            link_metadata = link_metadata_from_events(link_events)
            if (
                link_metadata is None
                or link_metadata.profile_name != _PROFILE_NAME
                or link_metadata.profile_reference != _PROFILE_NAME
                or link_metadata.configuration_fingerprint != profile_fingerprint
            ):
                raise RuntimeError(f"unexpected link metadata: {link_metadata}")

            _wait_until(
                listener,
                lambda: (
                    telemetry_path.is_file()
                    and len(load_telemetry_records(telemetry_path))
                    == link_statistics.deliveries_forwarded
                ),
                description="all forwarded telemetry deliveries",
            )
            _wait_until(
                listener,
                lambda: (
                    alarm_path.is_file()
                    and _alarm_codes(load_alarm_events(alarm_path)) >= _EXPECTED_ALARM_CODES
                ),
                description="expected alarm transitions",
            )
            listener_stdout, listener_stderr = _interrupt_and_collect(listener)
        except BaseException:
            if link_process is not None:
                _terminate(link_process)
            _terminate(listener, interrupt=True)
            raise

        if listener.returncode != 0 or listener_stderr.strip():
            raise RuntimeError(
                "installed listener failed: "
                f"returncode={listener.returncode} "
                f"stdout={listener_stdout.strip()!r} stderr={listener_stderr.strip()!r}"
            )

        simulator_lines = simulator_run.stdout.strip().splitlines()
        if (
            not simulator_lines
            or f"OrbitOps simulator {__version__}" not in simulator_lines[0]
            or "scenario=thermal" not in simulator_lines[0]
            or not any("mode=SAFE" in line for line in simulator_lines)
        ):
            raise RuntimeError(
                "simulator output does not match the installed package and thermal scenario: "
                f"python={__version__!r} stdout={simulator_run.stdout!r}"
            )

        telemetry_records = load_telemetry_records(telemetry_path)
        alarm_events = load_alarm_events(alarm_path)
        alarm_statistics_value = validate_alarm_summary(alarm_events)
        alarm_counters = {
            "transitions_raised": alarm_statistics_value.transitions_raised,
            "transitions_updated": alarm_statistics_value.transitions_updated,
            "transitions_cleared": alarm_statistics_value.transitions_cleared,
            "transitions_total": alarm_statistics_value.transitions_total,
        }
        if alarm_counters != _EXPECTED_ALARM_COUNTS:
            raise RuntimeError(
                "unexpected deterministic alarm counters: "
                f"expected={_EXPECTED_ALARM_COUNTS} actual={alarm_counters}"
            )
        alarm_metadata = alarm_metadata_from_events(alarm_events)
        if (
            alarm_metadata is None
            or alarm_metadata.policy_name != _POLICY_NAME
            or alarm_metadata.policy_reference != _POLICY_NAME
            or alarm_metadata.policy_fingerprint != policy_fingerprint
            or not _alarm_codes(alarm_events) >= _EXPECTED_ALARM_CODES
        ):
            raise RuntimeError(f"unexpected alarm evidence: metadata={alarm_metadata}")

        command = [
            executable,
            "session",
            "inspect",
            "--telemetry",
            str(telemetry_path),
            "--link-events",
            str(link_path),
            "--alarm-events",
            str(alarm_path),
        ]
        json_result = _run([*command, "--format", "json"])
        document = _parse_report(json_result.stdout)
        _validate_report(
            document,
            telemetry_count=len(telemetry_records),
            alarm_counters=alarm_counters,
            link_counters=link_counters,
            policy_fingerprint=policy_fingerprint,
            profile_fingerprint=profile_fingerprint,
        )

        text_result = _run([*command, "--limit", str(_TEXT_EVENT_LIMIT)])
        if (
            text_result.stderr
            or not text_result.stdout.startswith("OrbitOps session report\n")
            or "status: complete compatible\n" not in text_result.stdout
            or "timeline_truncated" not in text_result.stdout
        ):
            raise RuntimeError("bounded text report did not expose status and truncation")

    print("OrbitOps flagship session-inspection demo")
    print(listener_ready)
    print(link_ready)
    print(simulator_lines[0])
    print(simulator_lines[-1])
    print()
    print(text_result.stdout.rstrip())
    print()
    print(
        "session inspection demo ok: "
        f"version={__version__} "
        f"profile={_PROFILE_NAME} "
        f"policy={_POLICY_NAME} "
        f"received={link_statistics.packets_received} "
        f"dropped={link_statistics.packets_dropped} "
        f"delayed={link_statistics.packets_delayed} "
        f"forwarded={link_statistics.deliveries_forwarded} "
        f"alarms={alarm_statistics_value.transitions_total} "
        f"timeline={document['summary']['timeline_entries_total']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

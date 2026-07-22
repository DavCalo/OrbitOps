#!/usr/bin/env python3
"""Exercise the public session inspector through the active installed command."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import cast

from orbitops import __version__
from orbitops.alarm_events import (
    AlarmEvent,
    AlarmEventType,
    AlarmRunMetadata,
    AlarmRunStatistics,
)
from orbitops.link.events import LinkEvent, LinkEventType, LinkRunMetadata
from orbitops.link.statistics import LinkStatistics
from orbitops.protocol import Mode, TelemetryPacket, encode_packet
from orbitops.recorder import SessionRecorder
from orbitops.session import REPORT_FORMAT, REPORT_FORMAT_VERSION, SessionReportDocument

_EXPECTED_VERSION = "0.4.0"


def _write_jsonl(path: Path, documents: Iterable[Mapping[str, object]]) -> None:
    path.write_text(
        "".join(
            json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n"
            for document in documents
        ),
        encoding="utf-8",
    )


def _write_evidence(directory: Path) -> tuple[Path, Path, Path]:
    telemetry_path = directory / "telemetry.jsonl"
    alarm_path = directory / "alarm-events.jsonl"
    link_path = directory / "link-events.jsonl"

    with SessionRecorder(telemetry_path) as recorder:
        for offset, sequence in enumerate((10, 11)):
            recorder.write(
                encode_packet(
                    TelemetryPacket(
                        sequence=sequence,
                        timestamp_ms=sequence * 1000,
                        mode=Mode.NOMINAL,
                        battery_mv=8200,
                        bus_current_ma=240,
                        temperature_centi_c=2100,
                        roll_centi_deg=100,
                        pitch_centi_deg=-200,
                        yaw_centi_deg=300,
                    )
                ),
                100.0 + offset,
            )

    alarm_metadata = AlarmRunMetadata(
        policy_name="standard",
        policy_reference="builtin:standard",
        policy_schema_version=1,
        policy_fingerprint="sha256:" + "1" * 64,
    )
    alarm_events = (
        AlarmEvent(
            session_id="alarm-package-check",
            event_index=0,
            elapsed_ns=0,
            event_type=AlarmEventType.RUN_METADATA,
            attributes=alarm_metadata.to_attributes(),
        ),
        AlarmEvent(
            session_id="alarm-package-check",
            event_index=1,
            elapsed_ns=10,
            event_type=AlarmEventType.ALARM_RAISED,
            packet_sequence=11,
            attributes={
                "alarm_identity": "temperature",
                "code": "TEMP_HIGH",
                "message": "temperature exceeds threshold",
                "observed_value": 51.0,
                "severity": "warning",
                "threshold": 50.0,
            },
        ),
        AlarmEvent(
            session_id="alarm-package-check",
            event_index=2,
            elapsed_ns=20,
            event_type=AlarmEventType.RUN_SUMMARY,
            attributes=AlarmRunStatistics(transitions_raised=1).to_attributes(),
        ),
    )
    _write_jsonl(alarm_path, (event.to_dict() for event in alarm_events))

    link_metadata = LinkRunMetadata(
        configuration_fingerprint="sha256:" + "2" * 64,
        profile_name="nominal",
        profile_reference="builtin:nominal",
        profile_schema_version=1,
    )
    link_events = (
        LinkEvent(
            session_id="link-package-check",
            event_index=0,
            elapsed_ns=0,
            event_type=LinkEventType.RUN_METADATA,
            attributes=link_metadata.to_attributes(),
        ),
        LinkEvent(
            session_id="link-package-check",
            event_index=1,
            elapsed_ns=5,
            event_type=LinkEventType.PACKET_RECEIVED,
            packet_index=0,
        ),
        LinkEvent(
            session_id="link-package-check",
            event_index=2,
            elapsed_ns=6,
            event_type=LinkEventType.PACKET_CORRUPTED,
            packet_index=0,
        ),
        LinkEvent(
            session_id="link-package-check",
            event_index=3,
            elapsed_ns=7,
            event_type=LinkEventType.RUN_SUMMARY,
            attributes=LinkStatistics(
                packets_received=1,
                packets_corrupted=1,
            ).to_dict(),
        ),
    )
    _write_jsonl(link_path, (event.to_dict() for event in link_events))
    return telemetry_path, link_path, alarm_path


def _run(command: list[str], expected_code: int) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != expected_code:
        raise RuntimeError(
            "installed session command returned an unexpected exit code: "
            f"expected={expected_code} actual={result.returncode} "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    return result


def _parse_report(text: str) -> SessionReportDocument:
    document: object = json.loads(text)
    if not isinstance(document, dict):
        raise RuntimeError("installed session command did not emit a JSON object")
    return cast(SessionReportDocument, document)


def _validate_complete_report(document: SessionReportDocument) -> None:
    metadata = document["metadata"]
    if metadata["report_format"] != REPORT_FORMAT:
        raise RuntimeError(f"unexpected report format: {metadata['report_format']!r}")
    if metadata["report_format_version"] != REPORT_FORMAT_VERSION:
        raise RuntimeError(
            f"unexpected report format version: {metadata['report_format_version']!r}"
        )

    summary = document["summary"]
    if not summary["complete"] or not summary["compatible"]:
        raise RuntimeError(f"installed complete report has unexpected status: {summary}")
    if summary["timeline_entries_total"] != 5:
        raise RuntimeError(f"unexpected complete timeline size: {summary}")

    sources = {source["lane"]: source for source in document["sources"]}
    if sources["telemetry"]["counters"]["packets_decoded"] != 2:
        raise RuntimeError("telemetry counters were not preserved")
    if sources["alarm"]["counters"]["transitions_total"] != 1:
        raise RuntimeError("alarm counters were not preserved")
    if sources["link"]["counters"]["packets_corrupted"] != 1:
        raise RuntimeError("link counters were not preserved")


def main() -> int:
    if __version__ != _EXPECTED_VERSION:
        raise RuntimeError(
            "unexpected installed OrbitOps version: "
            f"expected={_EXPECTED_VERSION!r} actual={__version__!r}"
        )

    executable = shutil.which("orbitops")
    if executable is None:
        raise RuntimeError("installed orbitops command was not found on PATH")

    with tempfile.TemporaryDirectory() as directory_name:
        directory = Path(directory_name)
        telemetry_path, link_path, alarm_path = _write_evidence(directory)
        base_command = [
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

        text_result = _run(base_command, 0)
        if text_result.stderr or not text_result.stdout.startswith("OrbitOps session report\n"):
            raise RuntimeError("installed text report was not emitted cleanly")
        if "status: complete compatible\n" not in text_result.stdout:
            raise RuntimeError("installed text report has an unexpected status")

        json_result = _run([*base_command, "--format", "json"], 0)
        if json_result.stderr:
            raise RuntimeError(f"installed JSON report wrote stderr: {json_result.stderr!r}")
        complete_document = _parse_report(json_result.stdout)
        _validate_complete_report(complete_document)

        filtered_result = _run(
            [
                *base_command,
                "--format",
                "json",
                "--sequence-min",
                "11",
                "--limit",
                "1",
            ],
            0,
        )
        filtered_document = _parse_report(filtered_result.stdout)
        selection = filtered_document["selection"]
        if not selection["timeline_truncated"]:
            raise RuntimeError("installed filtered report did not expose truncation")
        if selection["timeline_entries_rendered"] != 1:
            raise RuntimeError(f"unexpected rendered timeline count: {selection}")
        if selection["timeline_entries_matched"] != 2:
            raise RuntimeError(f"unexpected matching timeline count: {selection}")
        _validate_complete_report(filtered_document)

        output_path = directory / "session-report.json"
        output_path.write_text("previous report\n", encoding="utf-8")
        output_result = _run(
            [*base_command, "--format", "json", "--output", str(output_path)],
            0,
        )
        if output_result.stdout or output_result.stderr:
            raise RuntimeError("installed output mode unexpectedly wrote to the terminal")
        _validate_complete_report(_parse_report(output_path.read_text(encoding="utf-8")))

        incomplete_result = _run(
            [
                executable,
                "session",
                "inspect",
                "--telemetry",
                str(telemetry_path),
                "--format",
                "json",
            ],
            1,
        )
        incomplete_document = _parse_report(incomplete_result.stdout)
        incomplete_summary = incomplete_document["summary"]
        if incomplete_summary["complete"] or not incomplete_summary["compatible"]:
            raise RuntimeError(
                f"installed incomplete report has unexpected status: {incomplete_summary}"
            )

    print(
        "session inspection package ok: "
        f"version={__version__} "
        f"format={REPORT_FORMAT}/v{REPORT_FORMAT_VERSION} "
        "timeline=5 filtered=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

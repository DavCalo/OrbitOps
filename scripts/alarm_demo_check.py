#!/usr/bin/env python3
"""Exercise the installed OrbitOps CLI through a complete thermal alarm lifecycle."""

from __future__ import annotations

import selectors
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from orbitops.alarm_events import (
    AlarmEvent,
    AlarmEventType,
    AlarmRunStatistics,
    load_alarm_events,
    run_metadata_from_events,
    validate_run_summary,
)
from orbitops.alarm_policies import alarm_policy_fingerprint, load_builtin_alarm_policy

_PACKET_COUNT = 52
_POLICY_NAME = "thermal-demo"
_EXPECTED_TRANSITIONS = (
    (AlarmEventType.ALARM_RAISED, "ELEVATED_TEMPERATURE", "warning", 7),
    (AlarmEventType.ALARM_UPDATED, "HIGH_TEMPERATURE", "critical", 18),
    (AlarmEventType.ALARM_RAISED, "SAFE_MODE", "warning", 51),
)


def _reserve_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _installed_cli() -> str:
    executable = shutil.which("orbitops")
    if executable is None:
        raise RuntimeError(
            "installed orbitops CLI not found on PATH; run `python -m pip install -e .`"
        )
    return executable


def _wait_for_listener(process: subprocess.Popen[str]) -> str:
    if process.stdout is None:
        raise RuntimeError("listener stdout is unavailable")

    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout=5.0):
            raise RuntimeError("installed listener did not report readiness")
        line: str = process.stdout.readline().strip()
    finally:
        selector.close()

    if not line.startswith("OrbitOps ground station listening on udp://"):
        raise RuntimeError(f"unexpected listener output: {line!r}")
    return line


def _wait_for_events(
    path: Path,
    process: subprocess.Popen[str],
    predicate: Callable[[tuple[AlarmEvent, ...]], bool],
    *,
    description: str,
) -> tuple[AlarmEvent, ...]:
    deadline = time.monotonic() + 5.0
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"listener exited before {description}: returncode={process.returncode}"
            )
        if path.is_file():
            try:
                events = load_alarm_events(path)
            except (OSError, ValueError) as exc:
                last_error = exc
            else:
                if predicate(events):
                    return events
        time.sleep(0.02)

    detail = "" if last_error is None else f": last error={last_error}"
    raise RuntimeError(f"timed out waiting for {description}{detail}")


def _has_metadata(events: tuple[AlarmEvent, ...]) -> bool:
    return run_metadata_from_events(events) is not None


def _has_safe_mode(events: tuple[AlarmEvent, ...]) -> bool:
    return any(
        event.event_type is AlarmEventType.ALARM_RAISED
        and event.attributes.get("code") == "SAFE_MODE"
        for event in events
    )


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


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2.0)


def _transition_signature(
    events: Sequence[AlarmEvent],
) -> tuple[tuple[AlarmEventType, str, str, int], ...]:
    signature: list[tuple[AlarmEventType, str, str, int]] = []
    transition_types = {
        AlarmEventType.ALARM_RAISED,
        AlarmEventType.ALARM_UPDATED,
        AlarmEventType.ALARM_CLEARED,
    }
    for event in events:
        if event.event_type not in transition_types:
            continue
        code = event.attributes.get("code")
        severity = event.attributes.get("severity")
        sequence = event.packet_sequence
        if not isinstance(code, str):
            raise RuntimeError(f"alarm transition has invalid code: {event}")
        if not isinstance(severity, str):
            raise RuntimeError(f"alarm transition has invalid severity: {event}")
        if not isinstance(sequence, int):
            raise RuntimeError(f"alarm transition has invalid packet sequence: {event}")
        signature.append((event.event_type, code, severity, sequence))
    return tuple(signature)


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} PATH_TO_SIMULATOR", file=sys.stderr)
        return 2

    simulator = Path(sys.argv[1]).resolve()
    if not simulator.is_file():
        print(f"simulator not found: {simulator}", file=sys.stderr)
        return 2

    policy = load_builtin_alarm_policy(_POLICY_NAME)
    expected_fingerprint = alarm_policy_fingerprint(policy)
    listen_port = _reserve_udp_port()

    with tempfile.TemporaryDirectory() as directory:
        alarm_log = Path(directory) / "alarm-events.jsonl"
        listener = subprocess.Popen(
            [
                _installed_cli(),
                "listen",
                "--host",
                "127.0.0.1",
                "--port",
                str(listen_port),
                "--alarm-policy",
                _POLICY_NAME,
                "--alarm-log",
                str(alarm_log),
            ],
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        try:
            ready_line = _wait_for_listener(listener)
            _wait_for_events(
                alarm_log,
                listener,
                _has_metadata,
                description="alarm run metadata",
            )
            simulator_run = subprocess.run(
                [
                    str(simulator),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(listen_port),
                    "--packets",
                    str(_PACKET_COUNT),
                    "--interval-ms",
                    "5",
                    "--scenario",
                    "thermal",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=10.0,
            )
            _wait_for_events(
                alarm_log,
                listener,
                _has_safe_mode,
                description="SAFE-mode alarm transition",
            )
            listener_stdout, listener_stderr = _interrupt_and_collect(listener)
        except BaseException:
            _terminate(listener)
            raise

        if listener.returncode != 0:
            raise RuntimeError(
                "installed listener failed: "
                f"returncode={listener.returncode} "
                f"stdout={listener_stdout.strip()!r} "
                f"stderr={listener_stderr.strip()!r}"
            )
        if listener_stderr.strip():
            raise RuntimeError(f"installed listener wrote stderr: {listener_stderr.strip()!r}")
        if "scenario=thermal" not in simulator_run.stdout:
            raise RuntimeError("simulator output omitted the thermal scenario")
        if "mode=SAFE" not in simulator_run.stdout:
            raise RuntimeError("thermal scenario did not reach SAFE mode")

        events = load_alarm_events(alarm_log)
        metadata = run_metadata_from_events(events)
        if metadata is None:
            raise RuntimeError("alarm demo did not emit run metadata")
        if metadata.policy_name != _POLICY_NAME:
            raise RuntimeError(f"unexpected alarm-policy identity: {metadata}")
        if metadata.policy_reference != _POLICY_NAME:
            raise RuntimeError(f"unexpected alarm-policy reference: {metadata}")
        if metadata.policy_fingerprint != expected_fingerprint:
            raise RuntimeError(f"unexpected alarm-policy fingerprint: {metadata}")

        signature = _transition_signature(events)
        if signature != _EXPECTED_TRANSITIONS:
            raise RuntimeError(
                "unexpected alarm lifecycle ordering: "
                f"expected={_EXPECTED_TRANSITIONS!r} observed={signature!r}"
            )

        statistics = validate_run_summary(events)
        expected_statistics = AlarmRunStatistics(
            transitions_raised=2,
            transitions_updated=1,
            transitions_cleared=0,
        )
        if statistics != expected_statistics:
            raise RuntimeError(
                f"unexpected alarm transition counters: "
                f"expected={expected_statistics} observed={statistics}"
            )

    print(ready_line)
    print(simulator_run.stdout.strip())
    print(listener_stdout.strip())
    print(
        "alarm lifecycle demo ok: "
        f"policy={_POLICY_NAME} "
        f"fingerprint={expected_fingerprint} "
        f"raised={statistics.transitions_raised} "
        f"updated={statistics.transitions_updated} "
        f"cleared={statistics.transitions_cleared} "
        f"total={statistics.transitions_total}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

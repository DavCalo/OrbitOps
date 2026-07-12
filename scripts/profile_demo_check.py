#!/usr/bin/env python3
"""Exercise an installed OrbitOps CLI with a built-in mission profile."""

from __future__ import annotations

import selectors
import shutil
import socket
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from orbitops.link import (
    LinkEventType,
    configuration_fingerprint,
    load_link_events,
    run_metadata_from_events,
    validate_run_summary,
)
from orbitops.profiles import load_builtin_profile
from orbitops.protocol import decode_packet

_PACKET_COUNT = 16
_PROFILE_NAME = "intermittent-loss"


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


def _wait_for_ready(process: subprocess.Popen[str]) -> str:
    if process.stdout is None:
        raise RuntimeError("link process stdout is unavailable")

    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout=5.0):
            raise RuntimeError("installed link CLI did not report readiness")
        line: str = process.stdout.readline().strip()
    finally:
        selector.close()

    if not line.startswith("link ready:"):
        raise RuntimeError(f"unexpected link CLI output: {line!r}")
    return line


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2.0)


def _drain_receiver(receiver: socket.socket) -> list[int]:
    receiver.settimeout(0.2)
    sequences: list[int] = []
    while True:
        try:
            raw, _sender = receiver.recvfrom(4096)
        except TimeoutError:
            break
        sequences.append(decode_packet(raw).sequence)
    return sequences


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} PATH_TO_SIMULATOR", file=sys.stderr)
        return 2

    simulator = Path(sys.argv[1]).resolve()
    if not simulator.is_file():
        print(f"simulator not found: {simulator}", file=sys.stderr)
        return 2

    link_port = _reserve_udp_port()
    profile = load_builtin_profile(_PROFILE_NAME)
    expected_fingerprint = configuration_fingerprint(profile.link_config)

    with (
        tempfile.TemporaryDirectory() as directory,
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver,
    ):
        receiver.bind(("127.0.0.1", 0))
        forward_port = int(receiver.getsockname()[1])
        event_log = Path(directory) / "profile-events.jsonl"

        link_command = [
            _installed_cli(),
            "link",
            "--profile",
            _PROFILE_NAME,
            "--listen-host",
            "127.0.0.1",
            "--listen-port",
            str(link_port),
            "--forward-host",
            "127.0.0.1",
            "--forward-port",
            str(forward_port),
            "--event-log",
            str(event_log),
            "--session-id",
            "mission-profile-demo",
            "--max-packets",
            str(_PACKET_COUNT),
        ]
        link_process = subprocess.Popen(
            link_command,
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        try:
            ready_line = _wait_for_ready(link_process)
            completed = subprocess.run(
                [
                    str(simulator),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(link_port),
                    "--packets",
                    str(_PACKET_COUNT),
                    "--interval-ms",
                    "1",
                    "--scenario",
                    "nominal",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            stdout_tail, stderr = link_process.communicate(timeout=10.0)
            sequences = _drain_receiver(receiver)
        except BaseException:
            _terminate(link_process)
            raise

        if link_process.returncode != 0:
            raise RuntimeError(
                f"link CLI failed: stdout={stdout_tail.strip()!r} stderr={stderr.strip()!r}"
            )

        events = load_link_events(event_log)
        metadata = run_metadata_from_events(events)
        if metadata is None:
            raise RuntimeError("profile demo did not emit schema-versioned run metadata")
        if metadata.profile_name != _PROFILE_NAME:
            raise RuntimeError(f"unexpected profile identity: {metadata}")
        if metadata.profile_reference != _PROFILE_NAME:
            raise RuntimeError(f"unexpected profile reference: {metadata}")
        if metadata.configuration_fingerprint != expected_fingerprint:
            raise RuntimeError(f"unexpected effective configuration fingerprint: {metadata}")

        forwarded_indexes: list[int] = []
        for event in events:
            if event.event_type is not LinkEventType.PACKET_FORWARDED:
                continue
            if event.packet_index is None:
                raise RuntimeError("packet_forwarded event is missing packet_index")
            forwarded_indexes.append(event.packet_index)
        expected_sequences = Counter(forwarded_indexes)
        if Counter(sequences) != expected_sequences:
            raise RuntimeError(
                "forwarded packet events do not match decoded telemetry: "
                f"events={sorted(expected_sequences.elements())} received={sequences}"
            )

        statistics = validate_run_summary(events)
        if statistics.packets_received != _PACKET_COUNT:
            raise RuntimeError(f"unexpected received count: {statistics}")
        if statistics.packets_dropped != 2:
            raise RuntimeError(f"unexpected deterministic drop count: {statistics}")
        if statistics.packets_delayed != _PACKET_COUNT - 2:
            raise RuntimeError(f"unexpected delayed count: {statistics}")
        if statistics.deliveries_forwarded != len(sequences):
            raise RuntimeError(f"unexpected forwarded count: {statistics}")

    if f"profile={_PROFILE_NAME}" not in ready_line:
        raise RuntimeError(f"ready output omitted profile identity: {ready_line!r}")
    if f"config={expected_fingerprint}" not in ready_line:
        raise RuntimeError(f"ready output omitted configuration fingerprint: {ready_line!r}")

    print(ready_line)
    print(completed.stdout.strip())
    print(
        "mission profile demo ok: "
        f"profile={_PROFILE_NAME} "
        f"fingerprint={expected_fingerprint} "
        f"received={statistics.packets_received} "
        f"dropped={statistics.packets_dropped} "
        f"forwarded={statistics.deliveries_forwarded}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Exercise the public CLI across C++, the link emulator, and Python decoding."""

from __future__ import annotations

import os
import selectors
import socket
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.link import load_link_events, validate_run_summary  # noqa: E402
from orbitops.protocol import decode_packet  # noqa: E402

_PACKET_COUNT = 4


def _reserve_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_ready(process: subprocess.Popen[str]) -> str:
    if process.stdout is None:
        raise RuntimeError("link process stdout is unavailable")

    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout=5.0):
            raise RuntimeError("link CLI did not report readiness")
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


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} PATH_TO_SIMULATOR", file=sys.stderr)
        return 2

    simulator = Path(sys.argv[1]).resolve()
    if not simulator.is_file():
        print(f"simulator not found: {simulator}", file=sys.stderr)
        return 2

    link_port = _reserve_udp_port()
    with (
        tempfile.TemporaryDirectory() as directory,
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver,
    ):
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(5.0)
        forward_port = int(receiver.getsockname()[1])
        event_log = Path(directory) / "link-events.jsonl"

        environment = os.environ.copy()
        python_path = str(ROOT / "ground_station")
        existing_python_path = environment.get("PYTHONPATH")
        if existing_python_path:
            python_path = f"{python_path}{os.pathsep}{existing_python_path}"
        environment["PYTHONPATH"] = python_path
        environment["PYTHONUNBUFFERED"] = "1"

        link_command = [
            sys.executable,
            "-m",
            "orbitops",
            "link",
            "--listen-host",
            "127.0.0.1",
            "--listen-port",
            str(link_port),
            "--forward-host",
            "127.0.0.1",
            "--forward-port",
            str(forward_port),
            "--seed",
            "42",
            "--latency-ms",
            "5",
            "--duplicate-rate",
            "1",
            "--reorder-window",
            "2",
            "--event-log",
            str(event_log),
            "--session-id",
            "cli-integration",
            "--max-packets",
            str(_PACKET_COUNT),
        ]
        link_process = subprocess.Popen(
            link_command,
            cwd=ROOT,
            env=environment,
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

            sequences: list[int] = []
            for _ in range(_PACKET_COUNT * 2):
                raw, _sender = receiver.recvfrom(4096)
                sequences.append(decode_packet(raw).sequence)

            stdout_tail, stderr = link_process.communicate(timeout=5.0)
        except BaseException:
            _terminate(link_process)
            raise

        if link_process.returncode != 0:
            raise RuntimeError(
                f"link CLI failed: stdout={stdout_tail.strip()!r} stderr={stderr.strip()!r}"
            )

        expected = Counter({sequence: 2 for sequence in range(_PACKET_COUNT)})
        if Counter(sequences) != expected:
            raise RuntimeError(f"unexpected decoded sequence multiplicity: {sequences}")

        statistics = validate_run_summary(load_link_events(event_log))
        if statistics.packets_received != _PACKET_COUNT:
            raise RuntimeError(f"unexpected received count: {statistics}")
        if statistics.packets_delayed != _PACKET_COUNT:
            raise RuntimeError(f"unexpected delayed count: {statistics}")
        if statistics.packets_duplicated != _PACKET_COUNT:
            raise RuntimeError(f"unexpected duplicated count: {statistics}")
        if statistics.deliveries_forwarded != _PACKET_COUNT * 2:
            raise RuntimeError(f"unexpected forwarded count: {statistics}")

    print(ready_line)
    print(completed.stdout.strip())
    print(
        "public CLI demo ok: "
        f"packets={statistics.packets_received} "
        f"forwarded={statistics.deliveries_forwarded}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

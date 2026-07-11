#!/usr/bin/env python3
"""Verify that the C++ simulator emits a packet decoded by the Python station."""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.protocol import Mode, decode_packet  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} PATH_TO_SIMULATOR", file=sys.stderr)
        return 2

    simulator = Path(sys.argv[1]).resolve()
    if not simulator.is_file():
        print(f"simulator not found: {simulator}", file=sys.stderr)
        return 2

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.settimeout(3.0)
        port = sock.getsockname()[1]

        completed = subprocess.run(
            [
                str(simulator),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--packets",
                "1",
                "--interval-ms",
                "1",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        raw, _sender = sock.recvfrom(4096)

    packet = decode_packet(raw)
    if packet.sequence != 0 or packet.mode is not Mode.BOOT:
        raise SystemExit(f"unexpected packet: {packet}")

    print(completed.stdout.strip())
    print(f"cross-language decode ok: {len(raw)} bytes, sequence={packet.sequence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

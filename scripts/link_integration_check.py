#!/usr/bin/env python3
"""Verify C++ simulator -> link runtime -> Python protocol compatibility."""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.link import LinkConfig  # noqa: E402
from orbitops.link.runtime import LinkRuntime  # noqa: E402
from orbitops.protocol import Mode, decode_packet  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} PATH_TO_SIMULATOR", file=sys.stderr)
        return 2

    simulator = Path(sys.argv[1]).resolve()
    if not simulator.is_file():
        print(f"simulator not found: {simulator}", file=sys.stderr)
        return 2

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(3.0)

        runtime = LinkRuntime(
            ("127.0.0.1", 0),
            receiver.getsockname(),
            LinkConfig(),
        )
        runtime.open()
        thread = threading.Thread(target=runtime.run, kwargs={"max_packets": 1})
        thread.start()
        try:
            completed = subprocess.run(
                [
                    str(simulator),
                    "--host",
                    runtime.bound_address[0],
                    "--port",
                    str(runtime.bound_address[1]),
                    "--packets",
                    "1",
                    "--interval-ms",
                    "1",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            raw, _sender = receiver.recvfrom(4096)
        finally:
            thread.join(timeout=3.0)
            runtime.close()

    if thread.is_alive():
        raise SystemExit("link runtime did not stop")

    packet = decode_packet(raw)
    if packet.sequence != 0 or packet.mode is not Mode.BOOT:
        raise SystemExit(f"unexpected packet: {packet}")

    print(completed.stdout.strip())
    print(
        "link integration ok: "
        f"{len(raw)} bytes, sequence={packet.sequence}, path=simulator->emulator->station"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

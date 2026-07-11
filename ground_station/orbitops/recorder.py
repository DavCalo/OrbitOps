"""JSONL session recording and replay helpers."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path

RECORD_VERSION = 1


class SessionRecorder:
    """Write a deterministic, line-delimited telemetry capture.

    A new recorder replaces an existing file so repeated demos cannot silently
    mix multiple sessions. Use separate paths when captures must be preserved.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("w", encoding="utf-8")

    def write(self, raw_packet: bytes, received_at: float) -> None:
        record = {
            "record_version": RECORD_VERSION,
            "received_at": received_at,
            "packet_hex": raw_packet.hex(),
        }
        self._file.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> SessionRecorder:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


def iter_records(path: Path, speed: float = 1.0) -> Iterator[bytes]:
    if speed <= 0:
        raise ValueError("speed must be positive")

    previous_time: float | None = None
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                version = int(record["record_version"])
                timestamp = float(record["received_at"])
                packet = bytes.fromhex(record["packet_hex"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid record at line {line_number}") from exc

            if version != RECORD_VERSION:
                raise ValueError(f"unsupported record version {version} at line {line_number}")
            if previous_time is not None:
                delay = max(0.0, timestamp - previous_time) / speed
                time.sleep(delay)
            previous_time = timestamp
            yield packet

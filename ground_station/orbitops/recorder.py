"""JSONL session recording and replay helpers."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterator


class SessionRecorder:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("a", encoding="utf-8")

    def write(self, raw_packet: bytes, received_at: float) -> None:
        record = {
            "received_at": received_at,
            "packet_hex": raw_packet.hex(),
        }
        self._file.write(json.dumps(record, separators=(",", ":")) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "SessionRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
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
                timestamp = float(record["received_at"])
                packet = bytes.fromhex(record["packet_hex"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid record at line {line_number}") from exc

            if previous_time is not None:
                delay = max(0.0, timestamp - previous_time) / speed
                time.sleep(delay)
            previous_time = timestamp
            yield packet

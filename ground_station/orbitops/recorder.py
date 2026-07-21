"""JSONL session recording and replay helpers."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

RECORD_VERSION = 1
_RECORD_KEYS = frozenset({"packet_hex", "received_at", "record_version"})


def _validate_timestamp(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field} must be a real number")
    try:
        timestamp = float(value)
    except OverflowError as exc:
        raise ValueError(f"{field} must be finite") from exc
    if not math.isfinite(timestamp):
        raise ValueError(f"{field} must be finite")
    if timestamp < 0.0:
        raise ValueError(f"{field} must be non-negative")
    return timestamp


def _decode_record(payload: object, *, line_number: int) -> tuple[float, bytes]:
    if not isinstance(payload, dict):
        raise ValueError(f"invalid record at line {line_number}: record must be a JSON object")
    record = cast(dict[str, object], payload)
    if set(record) != _RECORD_KEYS:
        missing = sorted(_RECORD_KEYS - set(record))
        extra = sorted(set(record) - _RECORD_KEYS)
        raise ValueError(
            f"invalid record at line {line_number}: invalid keys: missing={missing}, extra={extra}"
        )

    version = record["record_version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(f"invalid record at line {line_number}: record_version must be an integer")
    if version != RECORD_VERSION:
        raise ValueError(f"unsupported record version {version} at line {line_number}")

    try:
        timestamp = _validate_timestamp(record["received_at"], field="received_at")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid record at line {line_number}: {exc}") from exc

    packet_hex = record["packet_hex"]
    if not isinstance(packet_hex, str):
        raise ValueError(f"invalid record at line {line_number}: packet_hex must be a string")
    try:
        packet = bytes.fromhex(packet_hex)
    except ValueError as exc:
        raise ValueError(f"invalid record at line {line_number}: packet_hex is invalid") from exc
    return timestamp, packet


@dataclass(frozen=True, slots=True)
class RecordedTelemetryRecord:
    """One validated telemetry-recording row without replay timing behavior."""

    record_index: int
    line_number: int
    received_at: float
    packet: bytes

    def __post_init__(self) -> None:
        if isinstance(self.record_index, bool) or not isinstance(self.record_index, int):
            raise TypeError("record_index must be an integer")
        if self.record_index < 0:
            raise ValueError("record_index must be non-negative")
        if isinstance(self.line_number, bool) or not isinstance(self.line_number, int):
            raise TypeError("line_number must be an integer")
        if self.line_number <= 0:
            raise ValueError("line_number must be positive")
        timestamp = _validate_timestamp(self.received_at, field="received_at")
        object.__setattr__(self, "received_at", timestamp)
        if not isinstance(self.packet, bytes):
            raise TypeError("packet must be bytes")


def _iter_decoded_records(path: Path) -> Iterator[RecordedTelemetryRecord]:
    record_index = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload: object = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid record at line {line_number}") from exc

            timestamp, packet = _decode_record(payload, line_number=line_number)
            yield RecordedTelemetryRecord(
                record_index=record_index,
                line_number=line_number,
                received_at=timestamp,
                packet=packet,
            )
            record_index += 1


def load_telemetry_records(path: Path) -> tuple[RecordedTelemetryRecord, ...]:
    """Load a telemetry recording strictly without replay sleeps."""

    return tuple(_iter_decoded_records(path))


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
        if not isinstance(raw_packet, bytes):
            raise TypeError("raw_packet must be bytes")
        timestamp = _validate_timestamp(received_at, field="received_at")
        record = {
            "record_version": RECORD_VERSION,
            "received_at": timestamp,
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
    if isinstance(speed, bool) or not isinstance(speed, int | float):
        raise TypeError("speed must be a real number")
    try:
        normalized_speed = float(speed)
    except OverflowError as exc:
        raise ValueError("speed must be positive and finite") from exc
    if not math.isfinite(normalized_speed) or normalized_speed <= 0.0:
        raise ValueError("speed must be positive and finite")

    previous_time: float | None = None
    for record in _iter_decoded_records(path):
        if previous_time is not None:
            delay = max(0.0, record.received_at - previous_time) / normalized_speed
            time.sleep(delay)
        previous_time = record.received_at
        yield record.packet

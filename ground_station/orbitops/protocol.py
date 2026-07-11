"""Binary OrbitOps telemetry protocol."""

from __future__ import annotations

import binascii
import enum
import struct
from dataclasses import asdict, dataclass
from typing import Any

MAGIC = b"ORBT"
VERSION = 1
_HEADER = struct.Struct("!4sBBIQBHHhhhh")
_PACKET = struct.Struct("!4sBBIQBHHhhhhI")
PACKET_SIZE = _PACKET.size


class ProtocolError(ValueError):
    """Raised when a telemetry packet is malformed or fails validation."""


class Mode(enum.IntEnum):
    BOOT = 0
    NOMINAL = 1
    SAFE = 2


@dataclass(frozen=True)
class TelemetryPacket:
    sequence: int
    timestamp_ms: int
    mode: Mode
    battery_mv: int
    bus_current_ma: int
    temperature_centi_c: int
    roll_centi_deg: int
    pitch_centi_deg: int
    yaw_centi_deg: int

    @property
    def battery_v(self) -> float:
        return self.battery_mv / 1000.0

    @property
    def temperature_c(self) -> float:
        return self.temperature_centi_c / 100.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = self.mode.name
        return payload


def _crc32(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


def _require_range(name: str, value: int, minimum: int, maximum: int) -> None:
    if not minimum <= value <= maximum:
        raise ProtocolError(f"{name} must be between {minimum} and {maximum}, got {value}")


def _validate_packet(packet: TelemetryPacket) -> None:
    _require_range("sequence", packet.sequence, 0, 0xFFFFFFFF)
    _require_range("timestamp_ms", packet.timestamp_ms, 0, 0xFFFFFFFFFFFFFFFF)
    _require_range("battery_mv", packet.battery_mv, 0, 0xFFFF)
    _require_range("bus_current_ma", packet.bus_current_ma, 0, 0xFFFF)
    for name, value in (
        ("temperature_centi_c", packet.temperature_centi_c),
        ("roll_centi_deg", packet.roll_centi_deg),
        ("pitch_centi_deg", packet.pitch_centi_deg),
        ("yaw_centi_deg", packet.yaw_centi_deg),
    ):
        _require_range(name, value, -0x8000, 0x7FFF)
    try:
        Mode(packet.mode)
    except ValueError as exc:
        raise ProtocolError(f"invalid mode: {packet.mode}") from exc


def encode_packet(packet: TelemetryPacket) -> bytes:
    _validate_packet(packet)
    body = _HEADER.pack(
        MAGIC,
        VERSION,
        0,
        packet.sequence,
        packet.timestamp_ms,
        int(packet.mode),
        packet.battery_mv,
        packet.bus_current_ma,
        packet.temperature_centi_c,
        packet.roll_centi_deg,
        packet.pitch_centi_deg,
        packet.yaw_centi_deg,
    )
    return body + struct.pack("!I", _crc32(body))


def decode_packet(data: bytes) -> TelemetryPacket:
    if len(data) != PACKET_SIZE:
        raise ProtocolError(f"expected {PACKET_SIZE} bytes, got {len(data)}")

    unpacked = _PACKET.unpack(data)
    magic, version, flags = unpacked[:3]
    received_crc = unpacked[-1]
    calculated_crc = _crc32(data[:-4])

    if magic != MAGIC:
        raise ProtocolError(f"invalid magic: {magic!r}")
    if version != VERSION:
        raise ProtocolError(f"unsupported version: {version}")
    if flags != 0:
        raise ProtocolError(f"unsupported flags: 0x{flags:02X}")
    if received_crc != calculated_crc:
        raise ProtocolError(
            f"CRC mismatch: received 0x{received_crc:08X}, calculated 0x{calculated_crc:08X}"
        )

    try:
        mode = Mode(unpacked[5])
    except ValueError as exc:
        raise ProtocolError(f"invalid mode: {unpacked[5]}") from exc

    return TelemetryPacket(
        sequence=unpacked[3],
        timestamp_ms=unpacked[4],
        mode=mode,
        battery_mv=unpacked[6],
        bus_current_ma=unpacked[7],
        temperature_centi_c=unpacked[8],
        roll_centi_deg=unpacked[9],
        pitch_centi_deg=unpacked[10],
        yaw_centi_deg=unpacked[11],
    )

from __future__ import annotations

import binascii
import struct
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.protocol import (  # noqa: E402
    PACKET_SIZE,
    Mode,
    ProtocolError,
    TelemetryPacket,
    decode_packet,
    encode_packet,
)


class ProtocolTests(unittest.TestCase):
    def sample(self) -> TelemetryPacket:
        return TelemetryPacket(
            sequence=42,
            timestamp_ms=1_726_000_000_123,
            mode=Mode.NOMINAL,
            battery_mv=8120,
            bus_current_ma=455,
            temperature_centi_c=2734,
            roll_centi_deg=-125,
            pitch_centi_deg=75,
            yaw_centi_deg=18250,
        )

    def test_round_trip(self) -> None:
        encoded = encode_packet(self.sample())
        self.assertEqual(len(encoded), PACKET_SIZE)
        self.assertEqual(decode_packet(encoded), self.sample())

    def test_crc_failure(self) -> None:
        encoded = bytearray(encode_packet(self.sample()))
        encoded[12] ^= 0x01
        with self.assertRaisesRegex(ProtocolError, "CRC mismatch"):
            decode_packet(bytes(encoded))

    def test_wrong_length(self) -> None:
        with self.assertRaisesRegex(ProtocolError, "expected"):
            decode_packet(b"short")

    def test_invalid_magic(self) -> None:
        encoded = bytearray(encode_packet(self.sample()))
        encoded[0:4] = b"FAIL"
        encoded[-4:] = struct.pack("!I", binascii.crc32(encoded[:-4]) & 0xFFFFFFFF)
        with self.assertRaisesRegex(ProtocolError, "invalid magic"):
            decode_packet(bytes(encoded))

    def test_unsupported_version(self) -> None:
        encoded = bytearray(encode_packet(self.sample()))
        encoded[4] = 2
        encoded[-4:] = struct.pack("!I", binascii.crc32(encoded[:-4]) & 0xFFFFFFFF)
        with self.assertRaisesRegex(ProtocolError, "unsupported version"):
            decode_packet(bytes(encoded))

    def test_nonzero_flags_are_rejected(self) -> None:
        encoded = bytearray(encode_packet(self.sample()))
        encoded[5] = 1
        encoded[-4:] = struct.pack("!I", binascii.crc32(encoded[:-4]) & 0xFFFFFFFF)
        with self.assertRaisesRegex(ProtocolError, "unsupported flags"):
            decode_packet(bytes(encoded))

    def test_invalid_mode_is_rejected(self) -> None:
        encoded = bytearray(encode_packet(self.sample()))
        encoded[18] = 99
        encoded[-4:] = struct.pack("!I", binascii.crc32(encoded[:-4]) & 0xFFFFFFFF)
        with self.assertRaisesRegex(ProtocolError, "invalid mode"):
            decode_packet(bytes(encoded))

    def test_encode_rejects_invalid_integer_field_types(self) -> None:
        fields = (
            "sequence",
            "timestamp_ms",
            "battery_mv",
            "bus_current_ma",
            "temperature_centi_c",
            "roll_centi_deg",
            "pitch_centi_deg",
            "yaw_centi_deg",
        )
        invalid_values: tuple[Any, ...] = (True, False, 1.5, "1")
        for field in fields:
            for invalid_value in invalid_values:
                with self.subTest(field=field, invalid_value=invalid_value):
                    invalid = replace(self.sample(), **{field: invalid_value})
                    with self.assertRaisesRegex(TypeError, rf"{field} must be an integer"):
                        encode_packet(invalid)

    def test_encode_preserves_integer_field_boundaries(self) -> None:
        boundaries: dict[str, tuple[Any, Any]] = {
            "sequence": (0, 0xFFFFFFFF),
            "timestamp_ms": (0, 0xFFFFFFFFFFFFFFFF),
            "battery_mv": (0, 0xFFFF),
            "bus_current_ma": (0, 0xFFFF),
            "temperature_centi_c": (-0x8000, 0x7FFF),
            "roll_centi_deg": (-0x8000, 0x7FFF),
            "pitch_centi_deg": (-0x8000, 0x7FFF),
            "yaw_centi_deg": (-0x8000, 0x7FFF),
        }
        for field, values in boundaries.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    packet = replace(self.sample(), **{field: value})
                    decoded = decode_packet(encode_packet(packet))
                    self.assertEqual(getattr(decoded, field), value)

    def test_encode_rejects_out_of_range_integer_field(self) -> None:
        invalid = TelemetryPacket(**{**self.sample().__dict__, "battery_mv": 70_000})
        with self.assertRaisesRegex(ProtocolError, "battery_mv"):
            encode_packet(invalid)

    def test_encode_validates_mode_type_and_domain(self) -> None:
        valid_modes: tuple[Any, ...] = (Mode.BOOT, Mode.NOMINAL, Mode.SAFE, 0, 1, 2)
        for valid_mode in valid_modes:
            with self.subTest(valid_mode=valid_mode):
                packet = replace(self.sample(), mode=valid_mode)
                decoded = decode_packet(encode_packet(packet))
                self.assertEqual(decoded.mode, Mode(int(valid_mode)))

        invalid_modes: tuple[Any, ...] = (True, False, 1.0, "1")
        for invalid_mode in invalid_modes:
            with self.subTest(invalid_mode=invalid_mode):
                packet = replace(self.sample(), mode=invalid_mode)
                with self.assertRaisesRegex(TypeError, "mode must be a Mode or integer"):
                    encode_packet(packet)

        invalid_mode_value: Any = 99
        invalid_value = replace(self.sample(), mode=invalid_mode_value)
        with self.assertRaisesRegex(ProtocolError, "invalid mode"):
            encode_packet(invalid_value)


if __name__ == "__main__":
    unittest.main()

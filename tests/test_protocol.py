from __future__ import annotations

import binascii
import struct
import sys
import unittest
from pathlib import Path

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

    def test_encode_validates_numeric_ranges(self) -> None:
        invalid = TelemetryPacket(**{**self.sample().__dict__, "battery_mv": 70_000})
        with self.assertRaisesRegex(ProtocolError, "battery_mv"):
            encode_packet(invalid)


if __name__ == "__main__":
    unittest.main()

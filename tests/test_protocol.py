from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.protocol import (  # noqa: E402
    Mode,
    PACKET_SIZE,
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


if __name__ == "__main__":
    unittest.main()

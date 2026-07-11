from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.alarms import AlarmEngine  # noqa: E402
from orbitops.protocol import Mode, TelemetryPacket  # noqa: E402


class AlarmTests(unittest.TestCase):
    def packet(
        self,
        sequence: int,
        *,
        temperature_centi_c: int = 2500,
        battery_mv: int = 8100,
        mode: Mode = Mode.NOMINAL,
    ) -> TelemetryPacket:
        return TelemetryPacket(
            sequence=sequence,
            timestamp_ms=0,
            mode=mode,
            battery_mv=battery_mv,
            bus_current_ma=400,
            temperature_centi_c=temperature_centi_c,
            roll_centi_deg=0,
            pitch_centi_deg=0,
            yaw_centi_deg=0,
        )

    def test_sequence_gap(self) -> None:
        engine = AlarmEngine()
        self.assertEqual(engine.evaluate(self.packet(5)), [])
        codes = {alarm.code for alarm in engine.evaluate(self.packet(7))}
        self.assertIn("SEQUENCE_GAP", codes)

    def test_sequence_wraparound_is_valid(self) -> None:
        engine = AlarmEngine()
        self.assertEqual(engine.evaluate(self.packet(0xFFFFFFFF)), [])
        self.assertNotIn(
            "SEQUENCE_GAP",
            {alarm.code for alarm in engine.evaluate(self.packet(0))},
        )

    def test_elevated_temperature_warning(self) -> None:
        engine = AlarmEngine()
        codes = {alarm.code for alarm in engine.evaluate(self.packet(1, temperature_centi_c=5200))}
        self.assertEqual(codes, {"ELEVATED_TEMPERATURE"})

    def test_critical_conditions(self) -> None:
        engine = AlarmEngine()
        codes = {
            alarm.code
            for alarm in engine.evaluate(
                self.packet(
                    1,
                    temperature_centi_c=6500,
                    battery_mv=6900,
                    mode=Mode.SAFE,
                )
            )
        }
        self.assertEqual(codes, {"HIGH_TEMPERATURE", "LOW_BATTERY", "SAFE_MODE"})


if __name__ == "__main__":
    unittest.main()

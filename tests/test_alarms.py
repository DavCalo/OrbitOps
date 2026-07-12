from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.alarm_policies import (  # noqa: E402
    ALARM_POLICY_SCHEMA_VERSION,
    AlarmPolicy,
    BatteryAlarmPolicy,
    ModeAlarmPolicy,
    SequenceAlarmPolicy,
    TemperatureAlarmPolicy,
)
from orbitops.alarms import (  # noqa: E402
    DEFAULT_ALARM_POLICY,
    Alarm,
    AlarmEngine,
    AlarmIdentity,
    AlarmSeverity,
    AlarmTransition,
    AlarmTransitionType,
    format_alarm_transition,
)
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

    def policy(
        self,
        *,
        temperature_hysteresis_c: float = 2.0,
        battery_hysteresis_v: float = 0.2,
        alarm_on_safe: bool = True,
        detect_gaps: bool = True,
    ) -> AlarmPolicy:
        return AlarmPolicy(
            schema_version=ALARM_POLICY_SCHEMA_VERSION,
            name="test-policy",
            description=None,
            temperature=TemperatureAlarmPolicy(
                warning_c=50.0,
                critical_c=60.0,
                hysteresis_c=temperature_hysteresis_c,
            ),
            battery=BatteryAlarmPolicy(
                critical_v=7.0,
                hysteresis_v=battery_hysteresis_v,
            ),
            mode=ModeAlarmPolicy(alarm_on_safe=alarm_on_safe),
            sequence=SequenceAlarmPolicy(detect_gaps=detect_gaps),
        )

    def test_default_policy_preserves_v03_thresholds(self) -> None:
        self.assertEqual(DEFAULT_ALARM_POLICY.temperature.warning_c, 50.0)
        self.assertEqual(DEFAULT_ALARM_POLICY.temperature.critical_c, 60.0)
        self.assertEqual(DEFAULT_ALARM_POLICY.temperature.hysteresis_c, 0.0)
        self.assertEqual(DEFAULT_ALARM_POLICY.battery.critical_v, 7.0)
        self.assertEqual(DEFAULT_ALARM_POLICY.battery.hysteresis_v, 0.0)

    def test_engine_rejects_non_policy_values(self) -> None:
        with self.assertRaises(TypeError):
            AlarmEngine(None)  # type: ignore[arg-type]

    def test_alarm_identity_rejects_empty_names(self) -> None:
        with self.assertRaises(ValueError):
            AlarmIdentity("")

    def test_warning_is_raised_once_for_repeated_packets(self) -> None:
        engine = AlarmEngine()
        first = engine.evaluate(self.packet(1, temperature_centi_c=5200))
        second = engine.evaluate(self.packet(2, temperature_centi_c=5300))

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].transition, AlarmTransitionType.RAISED)
        self.assertEqual(first[0].severity, AlarmSeverity.WARNING)
        self.assertEqual(first[0].code, "ELEVATED_TEMPERATURE")
        self.assertEqual(second, [])

    def test_direct_critical_temperature_is_raised(self) -> None:
        transition = AlarmEngine().evaluate(self.packet(1, temperature_centi_c=6500))[0]
        self.assertEqual(transition.transition, AlarmTransitionType.RAISED)
        self.assertEqual(transition.severity, AlarmSeverity.CRITICAL)
        self.assertEqual(transition.code, "HIGH_TEMPERATURE")

    def test_temperature_escalation_is_an_update(self) -> None:
        engine = AlarmEngine(self.policy())
        engine.evaluate(self.packet(1, temperature_centi_c=5200))
        transitions = engine.evaluate(self.packet(2, temperature_centi_c=6100))

        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0].identity.name, "temperature")
        self.assertEqual(transitions[0].transition, AlarmTransitionType.UPDATED)
        self.assertEqual(transitions[0].severity, AlarmSeverity.CRITICAL)
        self.assertEqual(transitions[0].code, "HIGH_TEMPERATURE")
        self.assertEqual(transitions[0].threshold, 60.0)

    def test_temperature_deescalates_after_critical_hysteresis(self) -> None:
        engine = AlarmEngine(self.policy())
        engine.evaluate(self.packet(1, temperature_centi_c=6100))

        self.assertEqual(engine.evaluate(self.packet(2, temperature_centi_c=5800)), [])
        transitions = engine.evaluate(self.packet(3, temperature_centi_c=5799))

        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0].transition, AlarmTransitionType.UPDATED)
        self.assertEqual(transitions[0].severity, AlarmSeverity.WARNING)
        self.assertEqual(transitions[0].code, "ELEVATED_TEMPERATURE")
        self.assertEqual(transitions[0].threshold, 58.0)

    def test_temperature_clears_only_beyond_warning_hysteresis(self) -> None:
        engine = AlarmEngine(self.policy())
        engine.evaluate(self.packet(1, temperature_centi_c=5100))

        self.assertEqual(engine.evaluate(self.packet(2, temperature_centi_c=4800)), [])
        transitions = engine.evaluate(self.packet(3, temperature_centi_c=4799))

        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0].transition, AlarmTransitionType.CLEARED)
        self.assertEqual(transitions[0].code, "ELEVATED_TEMPERATURE")
        self.assertEqual(transitions[0].threshold, 48.0)
        self.assertEqual(engine.active_alarm_identities, ())

    def test_critical_temperature_can_clear_directly(self) -> None:
        engine = AlarmEngine(self.policy())
        engine.evaluate(self.packet(1, temperature_centi_c=6200))
        transitions = engine.evaluate(self.packet(2, temperature_centi_c=4700))

        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0].transition, AlarmTransitionType.CLEARED)
        self.assertEqual(transitions[0].severity, AlarmSeverity.CRITICAL)
        self.assertEqual(transitions[0].code, "HIGH_TEMPERATURE")

    def test_low_battery_uses_recovery_hysteresis(self) -> None:
        engine = AlarmEngine(self.policy())
        raised = engine.evaluate(self.packet(1, battery_mv=6900))
        held = engine.evaluate(self.packet(2, battery_mv=7200))
        cleared = engine.evaluate(self.packet(3, battery_mv=7201))

        self.assertEqual(raised[0].transition, AlarmTransitionType.RAISED)
        self.assertEqual(raised[0].code, "LOW_BATTERY")
        self.assertEqual(held, [])
        self.assertEqual(cleared[0].transition, AlarmTransitionType.CLEARED)
        self.assertEqual(cleared[0].threshold, 7.2)

    def test_safe_mode_has_raise_and_clear_transitions(self) -> None:
        engine = AlarmEngine(self.policy())
        raised = engine.evaluate(self.packet(1, mode=Mode.SAFE))
        repeated = engine.evaluate(self.packet(2, mode=Mode.SAFE))
        cleared = engine.evaluate(self.packet(3, mode=Mode.NOMINAL))

        self.assertEqual(raised[0].transition, AlarmTransitionType.RAISED)
        self.assertEqual(raised[0].code, "SAFE_MODE")
        self.assertEqual(repeated, [])
        self.assertEqual(cleared[0].transition, AlarmTransitionType.CLEARED)

    def test_disabled_mode_and_sequence_alarms_emit_nothing(self) -> None:
        engine = AlarmEngine(self.policy(alarm_on_safe=False, detect_gaps=False))
        self.assertEqual(engine.evaluate(self.packet(5, mode=Mode.SAFE)), [])
        self.assertEqual(engine.evaluate(self.packet(8, mode=Mode.SAFE)), [])

    def test_sequence_gap_is_a_point_in_time_transition(self) -> None:
        engine = AlarmEngine()
        self.assertEqual(engine.evaluate(self.packet(5)), [])
        first_gap = engine.evaluate(self.packet(7))
        second_gap = engine.evaluate(self.packet(9))

        self.assertEqual(first_gap[0].transition, AlarmTransitionType.RAISED)
        self.assertEqual(first_gap[0].identity.name, "sequence-gap")
        self.assertEqual(first_gap[0].threshold, 6)
        self.assertEqual(second_gap[0].threshold, 8)
        self.assertNotIn(
            "sequence-gap",
            {identity.name for identity in engine.active_alarm_identities},
        )

    def test_sequence_wraparound_is_valid(self) -> None:
        engine = AlarmEngine()
        self.assertEqual(engine.evaluate(self.packet(0xFFFFFFFF)), [])
        self.assertEqual(engine.evaluate(self.packet(0)), [])

    def test_transition_order_is_deterministic(self) -> None:
        engine = AlarmEngine()
        engine.evaluate(self.packet(1))
        transitions = engine.evaluate(
            self.packet(
                3,
                temperature_centi_c=6500,
                battery_mv=6900,
                mode=Mode.SAFE,
            )
        )
        self.assertEqual(
            [transition.code for transition in transitions],
            ["SEQUENCE_GAP", "HIGH_TEMPERATURE", "LOW_BATTERY", "SAFE_MODE"],
        )

    def test_reset_clears_alarm_and_sequence_state(self) -> None:
        engine = AlarmEngine(self.policy())
        engine.evaluate(
            self.packet(
                5,
                temperature_centi_c=5200,
                battery_mv=6900,
                mode=Mode.SAFE,
            )
        )
        self.assertTrue(engine.active_alarm_identities)

        engine.reset()

        self.assertEqual(engine.active_alarm_identities, ())
        self.assertEqual(engine.evaluate(self.packet(8)), [])

    def test_transition_remains_compatible_with_alarm_base_type(self) -> None:
        transition = AlarmEngine().evaluate(self.packet(1, temperature_centi_c=6500))[0]
        self.assertIsInstance(transition, Alarm)
        self.assertIsInstance(transition, AlarmTransition)
        self.assertEqual(transition.severity, "critical")

    def test_raised_terminal_format_matches_previous_shape(self) -> None:
        transition = AlarmEngine().evaluate(self.packet(1, temperature_centi_c=6500))[0]
        self.assertEqual(
            format_alarm_transition(transition),
            "  !! CRITICAL HIGH_TEMPERATURE: temperature is 65.00 °C",
        )

    def test_updated_and_cleared_terminal_formats_show_lifecycle(self) -> None:
        engine = AlarmEngine(self.policy())
        engine.evaluate(self.packet(1, temperature_centi_c=5200))
        updated = engine.evaluate(self.packet(2, temperature_centi_c=6100))[0]
        cleared = engine.evaluate(self.packet(3, temperature_centi_c=4700))[0]

        self.assertIn("[UPDATED]", format_alarm_transition(updated))
        self.assertIn("[CLEARED]", format_alarm_transition(cleared))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.alarm_policies import (  # noqa: E402
    ALARM_POLICY_FINGERPRINT_SCHEMA_VERSION,
    ALARM_POLICY_SCHEMA_VERSION,
    AlarmPolicy,
    AlarmPolicyParseError,
    AlarmPolicyValidationError,
    BatteryAlarmPolicy,
    ModeAlarmPolicy,
    SequenceAlarmPolicy,
    TemperatureAlarmPolicy,
    alarm_policy_fingerprint,
    canonical_effective_alarm_policy,
    parse_alarm_policy,
)

FIXTURES = Path(__file__).with_name("fixtures") / "alarm_policies"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _standard_policy(*, name: str = "standard", description: str | None = None) -> AlarmPolicy:
    return AlarmPolicy(
        schema_version=1,
        name=name,
        description=description,
        temperature=TemperatureAlarmPolicy(50.0, 60.0, 0.0),
        battery=BatteryAlarmPolicy(7.0, 0.0),
        mode=ModeAlarmPolicy(True),
        sequence=SequenceAlarmPolicy(True),
    )


class AlarmPolicyModelTests(unittest.TestCase):
    def test_model_is_immutable_and_normalizes_numbers(self) -> None:
        policy = _standard_policy()
        self.assertIsInstance(policy.temperature.warning_c, float)
        self.assertIsInstance(policy.battery.critical_v, float)
        with self.assertRaises(FrozenInstanceError):
            policy.name = "changed"  # type: ignore[misc]

    def test_model_rejects_invalid_schema_identity_and_description(self) -> None:
        with self.assertRaises(TypeError):
            AlarmPolicy(cast(Any, True), "standard", None, *_standard_sections())
        with self.assertRaises(ValueError):
            AlarmPolicy(2, "standard", None, *_standard_sections())
        for name in ("", "Uppercase", "leading-", "-trailing", "has space", "a" * 65):
            with self.subTest(name=name), self.assertRaises(ValueError):
                AlarmPolicy(1, name, None, *_standard_sections())
        with self.assertRaises(ValueError):
            AlarmPolicy(1, "standard", "", *_standard_sections())
        with self.assertRaises(ValueError):
            AlarmPolicy(1, "standard", "contains\x00nul", *_standard_sections())

    def test_temperature_validation_rejects_invalid_bounds(self) -> None:
        invalid = (
            (60.0, 60.0, 0.0),
            (61.0, 60.0, 0.0),
            (50.0, 60.0, -1.0),
            (50.0, 60.0, 11.0),
            (float("nan"), 60.0, 0.0),
            (50.0, float("inf"), 0.0),
            (-1e308, 1e308, 1e308),
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises((TypeError, ValueError)):
                TemperatureAlarmPolicy(*values)
        with self.assertRaises(TypeError):
            TemperatureAlarmPolicy(cast(Any, True), 60.0, 0.0)

    def test_battery_and_boolean_sections_are_strict(self) -> None:
        for values in (
            (0.0, 0.0),
            (-1.0, 0.0),
            (7.0, -0.1),
            (float("inf"), 0.0),
            (1e308, 1e308),
        ):
            with self.subTest(values=values), self.assertRaises((TypeError, ValueError)):
                BatteryAlarmPolicy(*values)
        with self.assertRaises(TypeError):
            BatteryAlarmPolicy(cast(Any, True), 0.0)
        with self.assertRaises(TypeError):
            ModeAlarmPolicy(cast(Any, 1))
        with self.assertRaises(TypeError):
            SequenceAlarmPolicy(cast(Any, "yes"))

    def test_policy_rejects_wrong_section_types(self) -> None:
        temperature, battery, mode, sequence = _standard_sections()
        with self.assertRaises(TypeError):
            AlarmPolicy(1, "standard", None, cast(Any, object()), battery, mode, sequence)
        with self.assertRaises(TypeError):
            AlarmPolicy(1, "standard", None, temperature, cast(Any, object()), mode, sequence)


class AlarmPolicyParserTests(unittest.TestCase):
    def test_standard_fixture_matches_v030_thresholds(self) -> None:
        policy = parse_alarm_policy(_fixture("standard.toml"), source="standard.toml")
        self.assertEqual(policy.schema_version, ALARM_POLICY_SCHEMA_VERSION)
        self.assertEqual(policy, _standard_policy(description=policy.description))

    def test_parser_maps_every_section(self) -> None:
        document = """
schema_version = 1
name = "custom"
[temperature]
warning_c = 45
critical_c = 55
hysteresis_c = 2
[battery]
critical_v = 7.2
hysteresis_v = 0.15
[mode]
alarm_on_safe = false
[sequence]
detect_gaps = false
"""
        policy = parse_alarm_policy(document)
        self.assertEqual(policy.temperature, TemperatureAlarmPolicy(45.0, 55.0, 2.0))
        self.assertEqual(policy.battery, BatteryAlarmPolicy(7.2, 0.15))
        self.assertEqual(policy.mode, ModeAlarmPolicy(False))
        self.assertEqual(policy.sequence, SequenceAlarmPolicy(False))

    def test_malformed_toml_reports_source(self) -> None:
        with self.assertRaisesRegex(AlarmPolicyParseError, r"broken\.toml: invalid TOML"):
            parse_alarm_policy("schema_version = [", source="broken.toml")

    def test_unknown_top_level_and_section_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(
            AlarmPolicyValidationError,
            r"unknown top-level key\(s\): operator",
        ):
            parse_alarm_policy(_fixture("invalid-unknown-key.toml"))
        document = _fixture("standard.toml").replace(
            "hysteresis_c = 0.0",
            "hysteresis_c = 0.0\nrate_limit = 2",
        )
        with self.assertRaisesRegex(
            AlarmPolicyValidationError,
            r"unknown temperature key\(s\): rate_limit",
        ):
            parse_alarm_policy(document)

    def test_missing_required_keys_are_sorted(self) -> None:
        with self.assertRaisesRegex(
            AlarmPolicyValidationError,
            r"missing required key\(s\): battery, mode, sequence, temperature",
        ):
            parse_alarm_policy('schema_version = 1\nname = "incomplete"\n')

    def test_sections_must_be_tables_and_complete(self) -> None:
        document = _fixture("standard.toml").replace(
            "[temperature]\nwarning_c = 50.0\ncritical_c = 60.0\nhysteresis_c = 0.0",
            'temperature = "invalid"',
        )
        with self.assertRaisesRegex(AlarmPolicyValidationError, "temperature must be a TOML table"):
            parse_alarm_policy(document)
        document = _fixture("standard.toml").replace("hysteresis_v = 0.0\n", "")
        with self.assertRaisesRegex(
            AlarmPolicyValidationError,
            r"missing required battery key\(s\): hysteresis_v",
        ):
            parse_alarm_policy(document)

    def test_unsupported_schema_boolean_numbers_and_nonfinite_are_rejected(self) -> None:
        documents = (
            _fixture("standard.toml").replace("schema_version = 1", "schema_version = 2"),
            _fixture("standard.toml").replace("warning_c = 50.0", "warning_c = true"),
            _fixture("standard.toml").replace("critical_v = 7.0", 'critical_v = "low"'),
            _fixture("standard.toml").replace("warning_c = 50.0", "warning_c = nan"),
            _fixture("standard.toml").replace("critical_v = 7.0", "critical_v = inf"),
        )
        for document in documents:
            with self.subTest(document=document), self.assertRaises(AlarmPolicyValidationError):
                parse_alarm_policy(document)

    def test_invalid_ordering_and_hysteresis_are_rejected(self) -> None:
        documents = (
            _fixture("standard.toml").replace("warning_c = 50.0", "warning_c = 60.0"),
            _fixture("standard.toml").replace("hysteresis_c = 0.0", "hysteresis_c = 11.0"),
            _fixture("standard.toml").replace("hysteresis_v = 0.0", "hysteresis_v = -0.1"),
        )
        for document in documents:
            with self.subTest(document=document), self.assertRaises(AlarmPolicyValidationError):
                parse_alarm_policy(document)

    def test_document_and_source_types_are_strict(self) -> None:
        with self.assertRaises(TypeError):
            parse_alarm_policy(cast(Any, b"schema_version = 1"))
        with self.assertRaises(TypeError):
            parse_alarm_policy("", source=cast(Any, Path("policy.toml")))
        with self.assertRaises(ValueError):
            parse_alarm_policy("", source="")


class AlarmPolicyFingerprintTests(unittest.TestCase):
    def test_equivalent_documents_have_equal_model_and_fingerprint(self) -> None:
        first = parse_alarm_policy(_fixture("standard.toml"))
        second = parse_alarm_policy(
            """
name="other"
schema_version=1
[sequence]
detect_gaps=true
[mode]
alarm_on_safe=true
[battery]
hysteresis_v=0
critical_v=7
[temperature]
hysteresis_c=0
critical_c=60
warning_c=50
"""
        )
        self.assertEqual(first.temperature, second.temperature)
        self.assertEqual(first.battery, second.battery)
        self.assertEqual(alarm_policy_fingerprint(first), alarm_policy_fingerprint(second))

    def test_identity_metadata_does_not_change_fingerprint(self) -> None:
        first = _standard_policy(name="first", description="First")
        second = _standard_policy(name="second", description="Second")
        self.assertEqual(alarm_policy_fingerprint(first), alarm_policy_fingerprint(second))

    def test_canonical_policy_has_golden_representation(self) -> None:
        self.assertEqual(ALARM_POLICY_FINGERPRINT_SCHEMA_VERSION, 1)
        self.assertEqual(
            canonical_effective_alarm_policy(_standard_policy()),
            '{"battery":{"critical_v":"0x1.c000000000000p+2",'
            '"hysteresis_v":"0x0.0p+0"},"mode":{"alarm_on_safe":true},'
            '"schema_version":1,"sequence":{"detect_gaps":true},'
            '"temperature":{"critical_c":"0x1.e000000000000p+5",'
            '"hysteresis_c":"0x0.0p+0","warning_c":"0x1.9000000000000p+5"}}',
        )

    def test_standard_policy_has_golden_fingerprint(self) -> None:
        self.assertEqual(
            alarm_policy_fingerprint(_standard_policy()),
            "sha256:896434f1a10b2f021f9a6f18b2e8c5b28bb43931202848f87dc449b99213e2e2",
        )

    def test_each_effective_field_changes_fingerprint(self) -> None:
        baseline = alarm_policy_fingerprint(_standard_policy())
        variants = (
            AlarmPolicy(1, "x", None, TemperatureAlarmPolicy(49, 60, 0), *_other_sections()),
            AlarmPolicy(1, "x", None, TemperatureAlarmPolicy(50, 61, 0), *_other_sections()),
            AlarmPolicy(1, "x", None, TemperatureAlarmPolicy(50, 60, 1), *_other_sections()),
            AlarmPolicy(
                1,
                "x",
                None,
                TemperatureAlarmPolicy(50, 60, 0),
                BatteryAlarmPolicy(7.1, 0),
                ModeAlarmPolicy(True),
                SequenceAlarmPolicy(True),
            ),
            AlarmPolicy(
                1,
                "x",
                None,
                TemperatureAlarmPolicy(50, 60, 0),
                BatteryAlarmPolicy(7, 0.1),
                ModeAlarmPolicy(True),
                SequenceAlarmPolicy(True),
            ),
            AlarmPolicy(
                1,
                "x",
                None,
                TemperatureAlarmPolicy(50, 60, 0),
                BatteryAlarmPolicy(7, 0),
                ModeAlarmPolicy(False),
                SequenceAlarmPolicy(True),
            ),
            AlarmPolicy(
                1,
                "x",
                None,
                TemperatureAlarmPolicy(50, 60, 0),
                BatteryAlarmPolicy(7, 0),
                ModeAlarmPolicy(True),
                SequenceAlarmPolicy(False),
            ),
        )
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertNotEqual(alarm_policy_fingerprint(variant), baseline)

    def test_fingerprint_requires_alarm_policy(self) -> None:
        with self.assertRaises(TypeError):
            canonical_effective_alarm_policy(cast(Any, object()))
        with self.assertRaises(TypeError):
            alarm_policy_fingerprint(cast(Any, object()))


def _standard_sections() -> tuple[
    TemperatureAlarmPolicy,
    BatteryAlarmPolicy,
    ModeAlarmPolicy,
    SequenceAlarmPolicy,
]:
    return (
        TemperatureAlarmPolicy(50.0, 60.0, 0.0),
        BatteryAlarmPolicy(7.0, 0.0),
        ModeAlarmPolicy(True),
        SequenceAlarmPolicy(True),
    )


def _other_sections() -> tuple[BatteryAlarmPolicy, ModeAlarmPolicy, SequenceAlarmPolicy]:
    return BatteryAlarmPolicy(7.0, 0.0), ModeAlarmPolicy(True), SequenceAlarmPolicy(True)


if __name__ == "__main__":
    unittest.main()

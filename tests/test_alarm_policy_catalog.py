from __future__ import annotations

import sys
import unittest
from contextlib import chdir
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.alarm_policies import (  # noqa: E402
    AlarmPolicy,
    AlarmPolicyAmbiguousReferenceError,
    AlarmPolicyLoadError,
    AlarmPolicyNotFoundError,
    AlarmPolicyValidationError,
    BatteryAlarmPolicy,
    ModeAlarmPolicy,
    SequenceAlarmPolicy,
    TemperatureAlarmPolicy,
    alarm_policy_fingerprint,
    list_builtin_alarm_policies,
    load_alarm_policy_file,
    load_builtin_alarm_policy,
    resolve_alarm_policy,
)
from orbitops.alarms import DEFAULT_ALARM_POLICY  # noqa: E402


class BuiltinAlarmPolicyCatalogTests(unittest.TestCase):
    def test_catalog_has_stable_product_order(self) -> None:
        self.assertEqual(
            list_builtin_alarm_policies(),
            ("standard", "conservative", "thermal-demo", "power-demo"),
        )

    def test_every_builtin_loads_and_matches_its_resource_name(self) -> None:
        fingerprints: set[str] = set()
        for name in list_builtin_alarm_policies():
            with self.subTest(name=name):
                policy = load_builtin_alarm_policy(name)
                self.assertEqual(policy.name, name)
                fingerprints.add(alarm_policy_fingerprint(policy))
        self.assertEqual(len(fingerprints), len(list_builtin_alarm_policies()))

    def test_standard_builtin_is_backward_compatible(self) -> None:
        self.assertEqual(load_builtin_alarm_policy("standard"), DEFAULT_ALARM_POLICY)

    def test_builtin_policies_have_expected_thresholds(self) -> None:
        expected = {
            "standard": (50.0, 60.0, 0.0, 7.0, 0.0),
            "conservative": (45.0, 55.0, 2.0, 7.4, 0.2),
            "thermal-demo": (30.0, 38.0, 2.0, 7.0, 0.1),
            "power-demo": (50.0, 60.0, 1.0, 7.8, 0.15),
        }
        for name, values in expected.items():
            with self.subTest(name=name):
                policy = load_builtin_alarm_policy(name)
                self.assertEqual(
                    (
                        policy.temperature.warning_c,
                        policy.temperature.critical_c,
                        policy.temperature.hysteresis_c,
                        policy.battery.critical_v,
                        policy.battery.hysteresis_v,
                    ),
                    values,
                )

    def test_unknown_builtin_and_invalid_name_input_fail_clearly(self) -> None:
        with self.assertRaisesRegex(AlarmPolicyNotFoundError, "available policies"):
            load_builtin_alarm_policy("missing")
        with self.assertRaises(TypeError):
            load_builtin_alarm_policy(cast(Any, Path("standard")))
        with self.assertRaises(ValueError):
            load_builtin_alarm_policy("")

    def test_resource_identity_mismatch_is_rejected(self) -> None:
        mismatched = AlarmPolicy(
            schema_version=1,
            name="different",
            description=None,
            temperature=TemperatureAlarmPolicy(50.0, 60.0, 0.0),
            battery=BatteryAlarmPolicy(7.0, 0.0),
            mode=ModeAlarmPolicy(True),
            sequence=SequenceAlarmPolicy(True),
        )
        with (
            patch("orbitops.alarm_policies.catalog.parse_alarm_policy", return_value=mismatched),
            self.assertRaisesRegex(AlarmPolicyValidationError, "does not match"),
        ):
            load_builtin_alarm_policy("standard")


class ExternalAlarmPolicyLoadingTests(unittest.TestCase):
    def _standard_document(self) -> str:
        resource = ROOT / "ground_station/orbitops/alarm_policies/builtin/standard.toml"
        return resource.read_text(encoding="utf-8")

    def test_external_and_builtin_standard_policies_are_equal(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "standard.toml"
            path.write_text(self._standard_document(), encoding="utf-8")
            self.assertEqual(load_alarm_policy_file(path), load_builtin_alarm_policy("standard"))

    def test_missing_file_and_directory_are_not_policies(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(AlarmPolicyNotFoundError, "not a regular file"):
                load_alarm_policy_file(root / "missing.toml")
            with self.assertRaisesRegex(AlarmPolicyNotFoundError, "not a regular file"):
                load_alarm_policy_file(root)

    def test_non_utf8_file_is_rejected_as_load_failure(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_bytes(b"\xff\xfe")
            with self.assertRaisesRegex(AlarmPolicyLoadError, "not valid UTF-8"):
                load_alarm_policy_file(path)

    def test_path_input_is_strict_and_nonempty(self) -> None:
        with self.assertRaises(TypeError):
            load_alarm_policy_file(cast(Any, 7))
        with self.assertRaises(TypeError):
            load_alarm_policy_file(cast(Any, b"policy.toml"))
        with self.assertRaises(ValueError):
            load_alarm_policy_file("")


class AlarmPolicyResolutionTests(unittest.TestCase):
    def _standard_document(self) -> str:
        resource = ROOT / "ground_station/orbitops/alarm_policies/builtin/standard.toml"
        return resource.read_text(encoding="utf-8")

    def test_short_and_explicit_builtin_references_match(self) -> None:
        self.assertEqual(
            resolve_alarm_policy("standard"),
            resolve_alarm_policy("builtin:standard"),
        )

    def test_string_path_explicit_file_and_pathlike_references_match(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "standard.toml"
            path.write_text(self._standard_document(), encoding="utf-8")
            expected = load_alarm_policy_file(path)
            self.assertEqual(resolve_alarm_policy(str(path)), expected)
            self.assertEqual(resolve_alarm_policy(f"file:{path}"), expected)
            self.assertEqual(resolve_alarm_policy(path), expected)

    def test_ambiguous_short_reference_requires_explicit_namespace(self) -> None:
        with TemporaryDirectory() as directory, chdir(directory):
            Path("standard").write_text(self._standard_document(), encoding="utf-8")
            with self.assertRaisesRegex(
                AlarmPolicyAmbiguousReferenceError,
                r"builtin:standard.*file:standard",
            ):
                resolve_alarm_policy("standard")
            self.assertEqual(resolve_alarm_policy("builtin:standard").name, "standard")
            self.assertEqual(resolve_alarm_policy("file:standard").name, "standard")

    def test_missing_reference_reports_available_builtins(self) -> None:
        with self.assertRaisesRegex(AlarmPolicyNotFoundError, "available built-ins"):
            resolve_alarm_policy("does-not-exist")
        with self.assertRaises(AlarmPolicyNotFoundError):
            resolve_alarm_policy("builtin:does-not-exist")
        with self.assertRaises(AlarmPolicyNotFoundError):
            resolve_alarm_policy("file:does-not-exist.toml")

    def test_empty_references_are_rejected(self) -> None:
        for reference in ("", "builtin:", "file:"):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                resolve_alarm_policy(reference)

    def test_external_validation_errors_retain_file_source(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_text(
                'schema_version = 1\nname = "invalid"\n[temperature]\nwarning_c = 50\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AlarmPolicyValidationError, r"file:.*invalid\.toml"):
                resolve_alarm_policy(path)


if __name__ == "__main__":
    unittest.main()

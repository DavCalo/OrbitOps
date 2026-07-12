from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.link import LinkConfig  # noqa: E402
from orbitops.profiles import (  # noqa: E402
    MISSION_PROFILE_SCHEMA_VERSION,
    MissionProfile,
    MissionProfileParseError,
    MissionProfileValidationError,
    canonical_effective_config,
    configuration_fingerprint,
    parse_mission_profile,
)

FIXTURES = Path(__file__).with_name("fixtures") / "profiles"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


class MissionProfileModelTests(unittest.TestCase):
    def test_model_is_immutable(self) -> None:
        profile = MissionProfile(
            schema_version=1,
            name="nominal",
            description=None,
            link_config=LinkConfig(),
        )
        with self.assertRaises(FrozenInstanceError):
            profile.name = "changed"  # type: ignore[misc]

    def test_model_rejects_invalid_schema_and_identity(self) -> None:
        with self.assertRaises(TypeError):
            MissionProfile(cast(Any, True), "nominal", None, LinkConfig())
        with self.assertRaises(ValueError):
            MissionProfile(2, "nominal", None, LinkConfig())
        with self.assertRaises(TypeError):
            MissionProfile(1, cast(Any, 7), None, LinkConfig())
        for name in ("", "Uppercase", "leading-", "-trailing", "has space", "a" * 65):
            with self.subTest(name=name), self.assertRaises(ValueError):
                MissionProfile(1, name, None, LinkConfig())

    def test_model_rejects_invalid_description_and_link_type(self) -> None:
        with self.assertRaises(TypeError):
            MissionProfile(1, "nominal", cast(Any, 7), LinkConfig())
        with self.assertRaises(ValueError):
            MissionProfile(1, "nominal", "", LinkConfig())
        with self.assertRaises(ValueError):
            MissionProfile(1, "nominal", "a" * 501, LinkConfig())
        with self.assertRaises(ValueError):
            MissionProfile(1, "nominal", "contains\x00nul", LinkConfig())
        with self.assertRaises(TypeError):
            MissionProfile(1, "nominal", None, cast(Any, object()))


class MissionProfileParserTests(unittest.TestCase):
    def test_nominal_fixture_uses_exact_link_defaults(self) -> None:
        profile = parse_mission_profile(_fixture("nominal.toml"), source="nominal.toml")
        self.assertEqual(profile.schema_version, MISSION_PROFILE_SCHEMA_VERSION)
        self.assertEqual(profile.name, "nominal")
        self.assertEqual(profile.link_config, LinkConfig())

    def test_degraded_fixture_maps_every_link_field(self) -> None:
        profile = parse_mission_profile(_fixture("degraded-link.toml"))
        self.assertEqual(
            profile.link_config,
            LinkConfig(
                seed=42,
                loss_rate=0.05,
                duplicate_rate=0.02,
                corrupt_rate=0.01,
                latency_ms=120,
                jitter_ms=30,
                reorder_window=3,
            ),
        )

    def test_malformed_toml_reports_the_source(self) -> None:
        with self.assertRaisesRegex(MissionProfileParseError, r"broken\.toml: invalid TOML"):
            parse_mission_profile("schema_version = [", source="broken.toml")

    def test_unknown_top_level_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            MissionProfileValidationError,
            r"unknown top-level key\(s\): operator",
        ):
            parse_mission_profile(_fixture("invalid-unknown-key.toml"))

    def test_unknown_link_key_is_rejected(self) -> None:
        document = 'schema_version = 1\nname = "invalid"\n[link]\nburst_rate = 0.2\n'
        with self.assertRaisesRegex(
            MissionProfileValidationError,
            r"unknown link key\(s\): burst_rate",
        ):
            parse_mission_profile(document)

    def test_missing_required_keys_are_reported_in_sorted_order(self) -> None:
        with self.assertRaisesRegex(
            MissionProfileValidationError,
            r"missing required key\(s\): link, name",
        ):
            parse_mission_profile("schema_version = 1")

    def test_link_must_be_a_table(self) -> None:
        document = 'schema_version = 1\nname = "invalid"\nlink = "not-a-table"\n'
        with self.assertRaisesRegex(MissionProfileValidationError, "link must be a TOML table"):
            parse_mission_profile(document)

    def test_unsupported_schema_version_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            MissionProfileValidationError,
            r"unsupported schema_version 2; expected 1",
        ):
            parse_mission_profile(_fixture("invalid-schema-version.toml"))

    def test_link_validation_reuses_link_config_bounds(self) -> None:
        documents = (
            'schema_version = 1\nname = "invalid"\n[link]\nloss_rate = 1.1\n',
            'schema_version = 1\nname = "invalid"\n[link]\nseed = -1\n',
            'schema_version = 1\nname = "invalid"\n[link]\nreorder_window = 65536\n',
        )
        for document in documents:
            with self.subTest(document=document), self.assertRaises(MissionProfileValidationError):
                parse_mission_profile(document)

    def test_boolean_and_non_numeric_link_values_are_rejected(self) -> None:
        documents = (
            'schema_version = 1\nname = "invalid"\n[link]\nseed = true\n',
            'schema_version = 1\nname = "invalid"\n[link]\nloss_rate = "often"\n',
        )
        for document in documents:
            with self.subTest(document=document), self.assertRaises(MissionProfileValidationError):
                parse_mission_profile(document)

    def test_name_and_description_types_are_rejected_by_parser(self) -> None:
        documents = (
            "schema_version = 1\nname = 7\n[link]\n",
            'schema_version = 1\nname = "invalid"\ndescription = 7\n[link]\n',
        )
        for document in documents:
            with self.subTest(document=document), self.assertRaises(MissionProfileValidationError):
                parse_mission_profile(document)

    def test_source_label_is_included_in_validation_errors(self) -> None:
        with self.assertRaisesRegex(MissionProfileValidationError, r"mission/profile\.toml:"):
            parse_mission_profile(
                'schema_version = 1\nname = "invalid"\n[link]\nlatency_ms = -1\n',
                source="mission/profile.toml",
            )

    def test_document_and_source_types_are_strict(self) -> None:
        with self.assertRaises(TypeError):
            parse_mission_profile(cast(Any, b"schema_version = 1"))
        with self.assertRaises(TypeError):
            parse_mission_profile("", source=cast(Any, Path("profile.toml")))
        with self.assertRaises(ValueError):
            parse_mission_profile("", source="")


class ConfigurationFingerprintTests(unittest.TestCase):
    def test_equivalent_toml_documents_resolve_identically(self) -> None:
        first = parse_mission_profile(
            'schema_version=1\nname="first"\n[link]\nloss_rate=0.10\nlatency_ms=5\n'
        )
        second = parse_mission_profile(
            'name = "second"\nschema_version = 1\n[link]\nlatency_ms = 5\nloss_rate = 0.1\n'
        )
        self.assertEqual(first.link_config, second.link_config)
        self.assertEqual(
            configuration_fingerprint(first.link_config),
            configuration_fingerprint(second.link_config),
        )

    def test_profile_metadata_does_not_change_effective_fingerprint(self) -> None:
        config = LinkConfig(seed=9, latency_ms=25)
        first = MissionProfile(1, "first", "One description.", config)
        second = MissionProfile(1, "second", "Another description.", config)
        self.assertEqual(
            configuration_fingerprint(first.link_config),
            configuration_fingerprint(second.link_config),
        )

    def test_canonical_configuration_has_a_golden_representation(self) -> None:
        config = LinkConfig(
            seed=42,
            loss_rate=0.05,
            duplicate_rate=0.02,
            corrupt_rate=0.01,
            latency_ms=120,
            jitter_ms=30,
            reorder_window=3,
        )
        self.assertEqual(
            canonical_effective_config(config),
            '{"link":{"corrupt_rate":"0x1.47ae147ae147bp-7",'
            '"duplicate_rate":"0x1.47ae147ae147bp-6",'
            '"jitter_ms":30,"latency_ms":120,'
            '"loss_rate":"0x1.999999999999ap-5","reorder_window":3,"seed":42},'
            '"schema_version":1}',
        )

    def test_fingerprint_has_a_golden_value(self) -> None:
        profile = parse_mission_profile(_fixture("degraded-link.toml"))
        self.assertEqual(
            configuration_fingerprint(profile.link_config),
            "sha256:c6b349115844c83d38de007d33f148d2e17ff6f280061e175477dd36c7074896",
        )

    def test_each_effective_field_changes_the_fingerprint(self) -> None:
        baseline = configuration_fingerprint(LinkConfig())
        variants = (
            LinkConfig(seed=1),
            LinkConfig(loss_rate=0.1),
            LinkConfig(duplicate_rate=0.1),
            LinkConfig(corrupt_rate=0.1),
            LinkConfig(latency_ms=1),
            LinkConfig(jitter_ms=1),
            LinkConfig(reorder_window=1),
        )
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertNotEqual(configuration_fingerprint(variant), baseline)

    def test_fingerprint_requires_link_config(self) -> None:
        with self.assertRaises(TypeError):
            canonical_effective_config(cast(Any, object()))
        with self.assertRaises(TypeError):
            configuration_fingerprint(cast(Any, object()))


if __name__ == "__main__":
    unittest.main()

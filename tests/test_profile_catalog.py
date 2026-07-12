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

from orbitops.link import LinkConfig  # noqa: E402
from orbitops.profiles import (  # noqa: E402
    MissionProfile,
    MissionProfileAmbiguousReferenceError,
    MissionProfileLoadError,
    MissionProfileNotFoundError,
    MissionProfileValidationError,
    configuration_fingerprint,
    list_builtin_profiles,
    load_builtin_profile,
    load_mission_profile_file,
    parse_mission_profile,
    resolve_mission_profile,
)

FIXTURES = Path(__file__).with_name("fixtures") / "profiles"


class BuiltinProfileCatalogTests(unittest.TestCase):
    def test_catalog_has_stable_product_order(self) -> None:
        self.assertEqual(
            list_builtin_profiles(),
            ("nominal", "intermittent-loss", "high-latency", "degraded-link"),
        )

    def test_every_builtin_profile_loads_and_matches_its_resource_name(self) -> None:
        fingerprints: set[str] = set()
        for name in list_builtin_profiles():
            with self.subTest(name=name):
                profile = load_builtin_profile(name)
                self.assertEqual(profile.name, name)
                fingerprints.add(configuration_fingerprint(profile.link_config))
        self.assertEqual(len(fingerprints), len(list_builtin_profiles()))

    def test_builtin_profiles_have_expected_effective_configurations(self) -> None:
        expected = {
            "nominal": LinkConfig(),
            "intermittent-loss": LinkConfig(
                seed=202_603,
                loss_rate=0.15,
                latency_ms=80,
                jitter_ms=20,
                reorder_window=1,
            ),
            "high-latency": LinkConfig(
                seed=202_604,
                loss_rate=0.01,
                latency_ms=750,
                jitter_ms=150,
                reorder_window=2,
            ),
            "degraded-link": LinkConfig(
                seed=42,
                loss_rate=0.05,
                duplicate_rate=0.02,
                corrupt_rate=0.01,
                latency_ms=120,
                jitter_ms=30,
                reorder_window=3,
            ),
        }
        for name, config in expected.items():
            with self.subTest(name=name):
                self.assertEqual(load_builtin_profile(name).link_config, config)

    def test_builtin_and_equivalent_external_profile_resolve_identically(self) -> None:
        builtin = load_builtin_profile("nominal")
        external = load_mission_profile_file(FIXTURES / "nominal.toml")
        self.assertEqual(external, builtin)

    def test_unknown_builtin_and_invalid_name_input_fail_clearly(self) -> None:
        with self.assertRaisesRegex(MissionProfileNotFoundError, "available profiles"):
            load_builtin_profile("missing")
        with self.assertRaises(TypeError):
            load_builtin_profile(cast(Any, Path("nominal")))
        with self.assertRaises(ValueError):
            load_builtin_profile("")

    def test_resource_identity_mismatch_is_rejected(self) -> None:
        mismatched = MissionProfile(1, "different", None, LinkConfig())
        with (
            patch("orbitops.profiles.catalog.parse_mission_profile", return_value=mismatched),
            self.assertRaisesRegex(MissionProfileValidationError, "does not match"),
        ):
            load_builtin_profile("nominal")


class ExternalProfileLoadingTests(unittest.TestCase):
    def test_external_file_loads_with_pathlike_input(self) -> None:
        profile = load_mission_profile_file(FIXTURES / "nominal.toml")
        self.assertEqual(profile.name, "nominal")
        self.assertEqual(profile.link_config, LinkConfig())

    def test_missing_file_and_directory_are_not_profiles(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(MissionProfileNotFoundError, "not a regular file"):
                load_mission_profile_file(root / "missing.toml")
            with self.assertRaisesRegex(MissionProfileNotFoundError, "not a regular file"):
                load_mission_profile_file(root)

    def test_non_utf8_file_is_rejected_as_load_failure(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_bytes(b"\xff\xfe")
            with self.assertRaisesRegex(MissionProfileLoadError, "not valid UTF-8"):
                load_mission_profile_file(path)

    def test_path_input_is_strict_and_nonempty(self) -> None:
        with self.assertRaises(TypeError):
            load_mission_profile_file(cast(Any, 7))
        with self.assertRaises(TypeError):
            load_mission_profile_file(cast(Any, b"profile.toml"))
        with self.assertRaises(ValueError):
            load_mission_profile_file("")


class MissionProfileResolutionTests(unittest.TestCase):
    def test_short_and_explicit_builtin_references_match(self) -> None:
        self.assertEqual(
            resolve_mission_profile("nominal"),
            resolve_mission_profile("builtin:nominal"),
        )

    def test_string_path_explicit_file_and_pathlike_references_match(self) -> None:
        path = FIXTURES / "nominal.toml"
        expected = load_mission_profile_file(path)
        self.assertEqual(resolve_mission_profile(str(path)), expected)
        self.assertEqual(resolve_mission_profile(f"file:{path}"), expected)
        self.assertEqual(resolve_mission_profile(path), expected)

    def test_ambiguous_short_reference_requires_explicit_namespace(self) -> None:
        with TemporaryDirectory() as directory, chdir(directory):
            Path("nominal").write_text((FIXTURES / "nominal.toml").read_text())
            with self.assertRaisesRegex(
                MissionProfileAmbiguousReferenceError,
                r"builtin:nominal.*file:nominal",
            ):
                resolve_mission_profile("nominal")
            self.assertEqual(resolve_mission_profile("builtin:nominal").name, "nominal")
            self.assertEqual(resolve_mission_profile("file:nominal").name, "nominal")

    def test_missing_reference_reports_available_builtins(self) -> None:
        with self.assertRaisesRegex(MissionProfileNotFoundError, "available built-ins"):
            resolve_mission_profile("does-not-exist")
        with self.assertRaises(MissionProfileNotFoundError):
            resolve_mission_profile("builtin:does-not-exist")
        with self.assertRaises(MissionProfileNotFoundError):
            resolve_mission_profile("file:does-not-exist.toml")

    def test_empty_references_are_rejected(self) -> None:
        for reference in ("", "builtin:", "file:"):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                resolve_mission_profile(reference)

    def test_resolved_external_validation_errors_retain_file_source(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.toml"
            path.write_text('schema_version = 1\nname = "invalid"\n[link]\nlatency_ms = -1\n')
            with self.assertRaisesRegex(MissionProfileValidationError, r"file:.*invalid\.toml"):
                resolve_mission_profile(path)

    def test_equivalent_documents_keep_the_same_fingerprint_after_resolution(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "custom.toml"
            path.write_text(
                'schema_version=1\nname="custom"\n[link]\nlatency_ms=5\nloss_rate=0.10\n'
            )
            first = resolve_mission_profile(path)
            second = parse_mission_profile(
                'name="other"\nschema_version=1\n[link]\nloss_rate=0.1\nlatency_ms=5\n'
            )
            self.assertEqual(
                configuration_fingerprint(first.link_config),
                configuration_fingerprint(second.link_config),
            )


if __name__ == "__main__":
    unittest.main()

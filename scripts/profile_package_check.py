#!/usr/bin/env python3
"""Smoke-test mission-profile resources from the active OrbitOps installation."""

from __future__ import annotations

from orbitops.profiles import (
    configuration_fingerprint,
    list_builtin_profiles,
    load_builtin_profile,
)

_EXPECTED_NAMES = ("nominal", "intermittent-loss", "high-latency", "degraded-link")


def main() -> int:
    names = list_builtin_profiles()
    if names != _EXPECTED_NAMES:
        raise RuntimeError(f"unexpected built-in profile catalog: {names!r}")

    fingerprints: set[str] = set()
    for name in names:
        profile = load_builtin_profile(name)
        if profile.name != name:
            raise RuntimeError(
                f"built-in profile identity mismatch: resource={name!r} profile={profile.name!r}"
            )
        fingerprint = configuration_fingerprint(profile.link_config)
        if fingerprint in fingerprints:
            raise RuntimeError(f"duplicate effective built-in configuration: {name!r}")
        fingerprints.add(fingerprint)
        print(f"{name}\t{fingerprint}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

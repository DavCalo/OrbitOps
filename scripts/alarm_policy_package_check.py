#!/usr/bin/env python3
"""Smoke-test alarm-policy resources from the active OrbitOps installation."""

from __future__ import annotations

from orbitops.alarm_policies import (
    alarm_policy_fingerprint,
    list_builtin_alarm_policies,
    load_builtin_alarm_policy,
)
from orbitops.alarms import DEFAULT_ALARM_POLICY

_EXPECTED_NAMES = ("standard", "conservative", "thermal-demo", "power-demo")


def main() -> int:
    names = list_builtin_alarm_policies()
    if names != _EXPECTED_NAMES:
        raise RuntimeError(f"unexpected built-in alarm-policy catalog: {names!r}")

    fingerprints: set[str] = set()
    for name in names:
        policy = load_builtin_alarm_policy(name)
        if policy.name != name:
            raise RuntimeError(
                f"built-in alarm-policy identity mismatch: resource={name!r} policy={policy.name!r}"
            )
        fingerprint = alarm_policy_fingerprint(policy)
        if fingerprint in fingerprints:
            raise RuntimeError(f"duplicate effective built-in alarm policy: {name!r}")
        fingerprints.add(fingerprint)
        print(f"{name}\t{fingerprint}")

    if load_builtin_alarm_policy("standard") != DEFAULT_ALARM_POLICY:
        raise RuntimeError("built-in standard policy does not match the default alarm policy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

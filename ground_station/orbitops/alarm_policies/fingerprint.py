"""Canonical effective alarm-policy encoding and fingerprinting."""

from __future__ import annotations

import hashlib
import json

from .model import AlarmPolicy

ALARM_POLICY_FINGERPRINT_SCHEMA_VERSION = 1


def canonical_effective_alarm_policy(policy: AlarmPolicy) -> str:
    """Return canonical JSON for behavior-affecting alarm-policy fields.

    Identity and descriptive metadata are excluded. Floating-point values use
    Python's exact hexadecimal representation for cross-platform stability.
    """

    if not isinstance(policy, AlarmPolicy):
        raise TypeError("policy must be an AlarmPolicy instance")

    document = {
        "battery": {
            "critical_v": policy.battery.critical_v.hex(),
            "hysteresis_v": policy.battery.hysteresis_v.hex(),
        },
        "mode": {"alarm_on_safe": policy.mode.alarm_on_safe},
        "schema_version": ALARM_POLICY_FINGERPRINT_SCHEMA_VERSION,
        "sequence": {"detect_gaps": policy.sequence.detect_gaps},
        "temperature": {
            "critical_c": policy.temperature.critical_c.hex(),
            "hysteresis_c": policy.temperature.hysteresis_c.hex(),
            "warning_c": policy.temperature.warning_c.hex(),
        },
    }
    return json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def alarm_policy_fingerprint(policy: AlarmPolicy) -> str:
    """Return a SHA-256 reproducibility identifier, not an authenticity proof."""

    canonical = canonical_effective_alarm_policy(policy).encode("ascii")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"

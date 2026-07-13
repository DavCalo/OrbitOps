#!/usr/bin/env python3
"""Smoke-test alarm-event APIs from the active OrbitOps installation."""

from __future__ import annotations

import tempfile
from pathlib import Path

from orbitops import __version__
from orbitops.alarm_events import (
    ALARM_EVENT_SCHEMA_VERSION,
    AlarmEventRecorder,
    AlarmRunMetadata,
    AlarmRunStatistics,
    load_alarm_events,
    run_metadata_from_events,
    validate_run_summary,
)
from orbitops.alarm_policies import alarm_policy_fingerprint, load_builtin_alarm_policy

_EXPECTED_VERSION = "0.4.0"


def main() -> int:
    if __version__ != _EXPECTED_VERSION:
        raise RuntimeError(
            f"unexpected installed OrbitOps version: "
            f"expected={_EXPECTED_VERSION!r} actual={__version__!r}"
        )
    if ALARM_EVENT_SCHEMA_VERSION != 1:
        raise RuntimeError(f"unexpected alarm-event schema version: {ALARM_EVENT_SCHEMA_VERSION}")

    policy = load_builtin_alarm_policy("thermal-demo")
    metadata = AlarmRunMetadata.from_policy(
        policy,
        reference="builtin:thermal-demo",
    )
    clock_values = iter((100, 100))

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "alarm-events.jsonl"
        with AlarmEventRecorder(
            path,
            metadata,
            session_id="alarm-package-check",
            clock_ns=lambda: next(clock_values),
        ):
            pass

        events = load_alarm_events(path)

    loaded_metadata = run_metadata_from_events(events)
    if loaded_metadata != metadata:
        raise RuntimeError(
            f"installed alarm-event metadata mismatch: expected={metadata} actual={loaded_metadata}"
        )
    if metadata.policy_fingerprint != alarm_policy_fingerprint(policy):
        raise RuntimeError("installed alarm-policy fingerprint mismatch")

    statistics = validate_run_summary(events)
    if statistics != AlarmRunStatistics():
        raise RuntimeError(f"unexpected empty-run alarm statistics: {statistics}")

    print(
        "alarm event package ok: "
        f"version={__version__} "
        f"schema={ALARM_EVENT_SCHEMA_VERSION} "
        f"policy={metadata.policy_name} "
        f"fingerprint={metadata.policy_fingerprint}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

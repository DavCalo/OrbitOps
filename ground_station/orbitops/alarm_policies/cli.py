"""Command-line adapter for versioned OrbitOps alarm policies."""

from __future__ import annotations

import argparse
import json

from .catalog import list_builtin_alarm_policies, resolve_alarm_policy
from .fingerprint import alarm_policy_fingerprint
from .model import AlarmPolicy


def configure_alarm_policy_parser(parser: argparse.ArgumentParser) -> None:
    """Add alarm-policy inspection and validation subcommands."""

    subparsers = parser.add_subparsers(dest="alarm_policy_command", required=True)
    subparsers.add_parser(
        "list",
        help="list stable built-in alarm policy names",
        description="Print one stable built-in alarm policy name per line.",
    )

    show_parser = subparsers.add_parser(
        "show",
        help="show one resolved alarm policy",
        description="Resolve a built-in or external alarm policy and print stable JSON.",
    )
    show_parser.add_argument("reference")

    validate_parser = subparsers.add_parser(
        "validate",
        help="validate one alarm policy reference",
        description="Resolve and validate a built-in or external alarm policy.",
    )
    validate_parser.add_argument("reference")


def _policy_document(policy: AlarmPolicy) -> dict[str, object]:
    return {
        "battery": {
            "critical_v": policy.battery.critical_v,
            "hysteresis_v": policy.battery.hysteresis_v,
        },
        "description": policy.description,
        "fingerprint": alarm_policy_fingerprint(policy),
        "mode": {"alarm_on_safe": policy.mode.alarm_on_safe},
        "name": policy.name,
        "schema_version": policy.schema_version,
        "sequence": {"detect_gaps": policy.sequence.detect_gaps},
        "temperature": {
            "critical_c": policy.temperature.critical_c,
            "hysteresis_c": policy.temperature.hysteresis_c,
            "warning_c": policy.temperature.warning_c,
        },
    }


def _print_json(document: dict[str, object]) -> None:
    print(json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True))


def run_alarm_policy_command(args: argparse.Namespace) -> int:
    """Run one alarm-policy CLI operation."""

    command: str = args.alarm_policy_command
    if command == "list":
        for name in list_builtin_alarm_policies():
            print(name)
        return 0

    if command not in {"show", "validate"}:
        raise AssertionError(f"unhandled alarm-policy command: {command}")

    reference: str = args.reference
    try:
        policy = resolve_alarm_policy(reference)
    except ValueError as exc:
        raise SystemExit(f"alarm-policy {command} failed: {exc}") from exc

    if command == "show":
        _print_json(_policy_document(policy))
        return 0

    _print_json(
        {
            "fingerprint": alarm_policy_fingerprint(policy),
            "name": policy.name,
            "valid": True,
        }
    )
    return 0

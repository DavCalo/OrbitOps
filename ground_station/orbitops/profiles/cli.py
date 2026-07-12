"""Command-line adapter for versioned OrbitOps mission profiles."""

from __future__ import annotations

import argparse
import json

from .catalog import list_builtin_profiles, resolve_mission_profile
from .fingerprint import configuration_fingerprint
from .model import MissionProfile


def configure_profile_parser(parser: argparse.ArgumentParser) -> None:
    """Add mission-profile inspection and validation subcommands."""

    subparsers = parser.add_subparsers(dest="profile_command", required=True)
    subparsers.add_parser(
        "list",
        help="list stable built-in mission profile names",
        description="Print one stable built-in mission profile name per line.",
    )

    show_parser = subparsers.add_parser(
        "show",
        help="show one resolved mission profile",
        description="Resolve a built-in or external mission profile and print stable JSON.",
    )
    show_parser.add_argument("reference")

    validate_parser = subparsers.add_parser(
        "validate",
        help="validate one mission profile reference",
        description="Resolve and validate a built-in or external mission profile.",
    )
    validate_parser.add_argument("reference")


def _profile_document(profile: MissionProfile) -> dict[str, object]:
    config = profile.link_config
    return {
        "description": profile.description,
        "fingerprint": configuration_fingerprint(config),
        "link": {
            "corrupt_rate": config.corrupt_rate,
            "duplicate_rate": config.duplicate_rate,
            "jitter_ms": config.jitter_ms,
            "latency_ms": config.latency_ms,
            "loss_rate": config.loss_rate,
            "reorder_window": config.reorder_window,
            "seed": config.seed,
        },
        "name": profile.name,
        "schema_version": profile.schema_version,
    }


def _print_json(document: dict[str, object]) -> None:
    print(json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True))


def run_profile_command(args: argparse.Namespace) -> int:
    """Run one mission-profile CLI operation."""

    command: str = args.profile_command
    if command == "list":
        for name in list_builtin_profiles():
            print(name)
        return 0

    if command not in {"show", "validate"}:
        raise AssertionError(f"unhandled profile command: {command}")

    reference: str = args.reference
    try:
        profile = resolve_mission_profile(reference)
    except ValueError as exc:
        raise SystemExit(f"profile {command} failed: {exc}") from exc

    if command == "show":
        _print_json(_profile_document(profile))
        return 0

    _print_json(
        {
            "fingerprint": configuration_fingerprint(profile.link_config),
            "name": profile.name,
            "valid": True,
        }
    )
    return 0

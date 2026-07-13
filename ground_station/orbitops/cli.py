"""Command-line interface for the OrbitOps ground station and link emulator."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .alarm_policies import AlarmPolicy, resolve_alarm_policy
from .alarm_policies.cli import configure_alarm_policy_parser, run_alarm_policy_command
from .alarms import DEFAULT_ALARM_POLICY, AlarmEngine
from .link.cli import configure_link_parser, run_link_command
from .profiles.cli import configure_profile_parser, run_profile_command
from .protocol import ProtocolError, decode_packet
from .receiver import listen, process_packet
from .recorder import iter_records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orbitops",
        description="Receive, emulate, inspect, record, and replay OrbitOps telemetry.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    listen_parser = subparsers.add_parser("listen", help="listen for UDP telemetry")
    listen_parser.add_argument("--host", default="127.0.0.1")
    listen_parser.add_argument("--port", type=int, default=9000)
    listen_parser.add_argument("--record", type=Path)
    listen_parser.add_argument(
        "--alarm-policy",
        metavar="REFERENCE",
        help="built-in alarm policy name or local TOML file reference",
    )
    listen_parser.add_argument(
        "--alarm-log",
        type=Path,
        metavar="PATH",
        help="write versioned alarm lifecycle events as JSONL",
    )

    link_parser = subparsers.add_parser(
        "link",
        help="proxy UDP telemetry through deterministic link impairments",
        description=(
            "Forward UDP datagrams through deterministic loss, latency, jitter, "
            "duplication, corruption, and bounded reordering."
        ),
    )
    configure_link_parser(link_parser)

    profile_parser = subparsers.add_parser(
        "profile",
        help="list, inspect, and validate mission profiles",
    )
    configure_profile_parser(profile_parser)

    alarm_policy_parser = subparsers.add_parser(
        "alarm-policy",
        help="list, inspect, and validate alarm policies",
    )
    configure_alarm_policy_parser(alarm_policy_parser)

    replay_parser = subparsers.add_parser("replay", help="replay a JSONL session")
    replay_parser.add_argument("path", type=Path)
    replay_parser.add_argument("--speed", type=float, default=1.0)

    decode_parser = subparsers.add_parser("decode", help="decode one packet from hex")
    decode_parser.add_argument("packet_hex")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "listen":
        if not 1 <= args.port <= 65535:
            raise SystemExit("port must be between 1 and 65535")
        reference: str | None = args.alarm_policy
        effective_reference = "builtin:standard" if reference is None else reference
        try:
            policy: AlarmPolicy = (
                DEFAULT_ALARM_POLICY if reference is None else resolve_alarm_policy(reference)
            )
        except ValueError as exc:
            raise SystemExit(f"listen failed: {exc}") from exc
        try:
            listen(
                args.host,
                args.port,
                args.record,
                policy,
                args.alarm_log,
                effective_reference,
            )
        except KeyboardInterrupt:
            print("\nGround station stopped.")
        except OSError as exc:
            raise SystemExit(f"listen failed: {exc}") from exc
        return 0

    if args.command == "link":
        return run_link_command(args)

    if args.command == "profile":
        return run_profile_command(args)

    if args.command == "alarm-policy":
        return run_alarm_policy_command(args)

    if args.command == "replay":
        if args.speed <= 0:
            raise SystemExit("speed must be positive")
        if not args.path.is_file():
            raise SystemExit(f"session file not found: {args.path}")

        engine = AlarmEngine()
        try:
            for raw in iter_records(args.path, args.speed):
                process_packet(raw, engine)
        except KeyboardInterrupt:
            print("\nReplay stopped.")
        except (OSError, ValueError, ProtocolError) as exc:
            raise SystemExit(f"replay failed: {exc}") from exc
        return 0

    if args.command == "decode":
        try:
            packet = decode_packet(bytes.fromhex(args.packet_hex))
        except (ValueError, ProtocolError) as exc:
            raise SystemExit(f"decode failed: {exc}") from exc
        print(packet.to_dict())
        return 0

    raise AssertionError(f"unhandled command: {args.command}")

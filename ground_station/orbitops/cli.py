"""Command-line interface for the OrbitOps ground station."""

from __future__ import annotations

import argparse
from pathlib import Path

from .alarms import AlarmEngine
from .protocol import ProtocolError, decode_packet
from .receiver import listen, process_packet
from .recorder import iter_records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orbitops", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    listen_parser = subparsers.add_parser("listen", help="listen for UDP telemetry")
    listen_parser.add_argument("--host", default="127.0.0.1")
    listen_parser.add_argument("--port", type=int, default=9000)
    listen_parser.add_argument("--record", type=Path)

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
        try:
            listen(args.host, args.port, args.record)
        except KeyboardInterrupt:
            print("\nGround station stopped.")
        return 0

    if args.command == "replay":
        engine = AlarmEngine()
        try:
            for raw in iter_records(args.path, args.speed):
                process_packet(raw, engine)
        except KeyboardInterrupt:
            print("\nReplay stopped.")
        return 0

    if args.command == "decode":
        try:
            packet = decode_packet(bytes.fromhex(args.packet_hex))
        except (ValueError, ProtocolError) as exc:
            raise SystemExit(f"decode failed: {exc}") from exc
        print(packet.to_dict())
        return 0

    raise AssertionError(f"unhandled command: {args.command}")

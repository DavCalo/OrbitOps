"""Command-line adapter for the deterministic OrbitOps link emulator."""

from __future__ import annotations

import argparse
import math
import uuid
from contextlib import ExitStack
from pathlib import Path

from .config import LinkConfig
from .events import JsonlEventRecorder
from .runtime import LinkRuntime
from .statistics import LinkStatistics

_MAX_SEED = (1 << 64) - 1
_MAX_REORDER_WINDOW = 65_535


def _port(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1 <= parsed <= 65_535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return parsed


def _probability(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("rate must be a number") from exc
    if not math.isfinite(parsed) or not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("rate must be finite and between 0.0 and 1.0")
    return parsed


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def _positive_int(value: str) -> int:
    parsed = _non_negative_int(value)
    if parsed == 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _seed(value: str) -> int:
    parsed = _non_negative_int(value)
    if parsed > _MAX_SEED:
        raise argparse.ArgumentTypeError(f"seed must be at most {_MAX_SEED}")
    return parsed


def _reorder_window(value: str) -> int:
    parsed = _non_negative_int(value)
    if parsed > _MAX_REORDER_WINDOW:
        raise argparse.ArgumentTypeError(f"reorder window must be at most {_MAX_REORDER_WINDOW}")
    return parsed


def _non_empty(value: str) -> str:
    if not value.strip():
        raise argparse.ArgumentTypeError("value must be a non-empty string")
    return value


def configure_link_parser(parser: argparse.ArgumentParser) -> None:
    """Add the supported link-emulator options to one subcommand parser."""

    endpoints = parser.add_argument_group("endpoints")
    endpoints.add_argument("--listen-host", type=_non_empty, default="127.0.0.1")
    endpoints.add_argument("--listen-port", type=_port, default=9001)
    endpoints.add_argument("--forward-host", type=_non_empty, default="127.0.0.1")
    endpoints.add_argument("--forward-port", type=_port, default=9000)

    impairments = parser.add_argument_group("deterministic impairments")
    impairments.add_argument("--seed", type=_seed, default=0)
    impairments.add_argument("--loss-rate", type=_probability, default=0.0)
    impairments.add_argument("--duplicate-rate", type=_probability, default=0.0)
    impairments.add_argument("--corrupt-rate", type=_probability, default=0.0)
    impairments.add_argument("--latency-ms", type=_non_negative_int, default=0)
    impairments.add_argument("--jitter-ms", type=_non_negative_int, default=0)
    impairments.add_argument("--reorder-window", type=_reorder_window, default=0)

    observability = parser.add_argument_group("observability and lifecycle")
    observability.add_argument(
        "--event-log",
        type=Path,
        help="write versioned link events and the final run summary as JSONL",
    )
    observability.add_argument(
        "--session-id",
        type=_non_empty,
        help="stable identifier stored with every link event",
    )
    observability.add_argument(
        "--max-packets",
        type=_positive_int,
        help="stop after receiving this many packets and draining scheduled deliveries",
    )


def _format_statistics(statistics: LinkStatistics) -> str:
    return (
        f"received={statistics.packets_received} "
        f"dropped={statistics.packets_dropped} "
        f"delayed={statistics.packets_delayed} "
        f"duplicated={statistics.packets_duplicated} "
        f"corrupted={statistics.packets_corrupted} "
        f"reordered={statistics.packets_reordered} "
        f"forwarded={statistics.deliveries_forwarded}"
    )


def run_link_command(args: argparse.Namespace) -> int:
    """Validate CLI values, run the proxy, and report its final statistics."""

    session_id = args.session_id or uuid.uuid4().hex
    try:
        config = LinkConfig(
            seed=args.seed,
            loss_rate=args.loss_rate,
            duplicate_rate=args.duplicate_rate,
            corrupt_rate=args.corrupt_rate,
            latency_ms=args.latency_ms,
            jitter_ms=args.jitter_ms,
            reorder_window=args.reorder_window,
        )
        with ExitStack() as stack:
            recorder = (
                stack.enter_context(JsonlEventRecorder(args.event_log))
                if args.event_log is not None
                else None
            )
            runtime = LinkRuntime(
                (args.listen_host, args.listen_port),
                (args.forward_host, args.forward_port),
                config,
                event_sink=None if recorder is None else recorder.write,
                session_id=session_id,
            )
            runtime.open()
            try:
                listen_host, listen_port = runtime.bound_address
                print(
                    "link ready: "
                    f"{listen_host}:{listen_port} -> "
                    f"{args.forward_host}:{args.forward_port} "
                    f"session={session_id}",
                    flush=True,
                )
                runtime.run(max_packets=args.max_packets)
            finally:
                runtime.close()
            statistics = runtime.statistics
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise SystemExit(f"link failed: {exc}") from exc

    print(f"link complete: {_format_statistics(statistics)}")
    if args.event_log is not None:
        print(f"link events: {args.event_log}")
    return 0

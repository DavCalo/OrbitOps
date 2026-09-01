#!/usr/bin/env python3
"""Generate deterministic session evidence and benchmark the production inspection phases."""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypeAlias, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.session.inspection import (  # noqa: E402
    _load_session_evidence,
    _normalize_loaded_session,
)
from orbitops.session.reporting import (  # noqa: E402
    project_session_report,
    render_session_report_json,
)
from session_benchmark_support import (  # noqa: E402
    DATASET_FORMAT,
    DATASET_FORMAT_VERSION,
    DATASET_SCALES,
    current_rss_bytes,
    dataset_scale,
    load_dataset_manifest,
    peak_rss_bytes,
    smoke_scale,
    verify_dataset_files,
    write_dataset,
)

BENCHMARK_FORMAT = "orbitops.session_inspection_benchmark"
BENCHMARK_FORMAT_VERSION = 1
JsonObject: TypeAlias = dict[str, object]


def _positive_int(value: str) -> int:
    parsed = int(value, 10)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _non_negative_int(value: str) -> int:
    parsed = int(value, 10)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _git_commit_sha() -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    sha = result.stdout.strip()
    if result.returncode != 0 or len(sha) != 40:
        raise RuntimeError("benchmark requires a Git checkout with a resolvable HEAD commit")
    return sha


def _environment_document() -> JsonObject:
    return {
        "architecture": platform.machine(),
        "logical_cpu_count": os.cpu_count(),
        "os_release": platform.release(),
        "os_system": platform.system(),
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
    }


def _phase_document(wall_ns: int, cpu_ns: int) -> JsonObject:
    return {
        "cpu_seconds": cpu_ns / 1_000_000_000.0,
        "wall_seconds": wall_ns / 1_000_000_000.0,
    }


def _run_sample(dataset_root: Path) -> JsonObject:
    manifest = load_dataset_manifest(dataset_root)
    paths = verify_dataset_files(dataset_root, manifest)

    total_wall_start = time.perf_counter_ns()
    total_cpu_start = time.process_time_ns()

    wall_start = time.perf_counter_ns()
    cpu_start = time.process_time_ns()
    evidence = _load_session_evidence(
        telemetry_path=paths.telemetry,
        link_events_path=paths.link_events,
        alarm_events_path=paths.alarm_events,
    )
    load_wall_ns = time.perf_counter_ns() - wall_start
    load_cpu_ns = time.process_time_ns() - cpu_start

    wall_start = time.perf_counter_ns()
    cpu_start = time.process_time_ns()
    session = _normalize_loaded_session(evidence)
    normalize_wall_ns = time.perf_counter_ns() - wall_start
    normalize_cpu_ns = time.process_time_ns() - cpu_start

    wall_start = time.perf_counter_ns()
    cpu_start = time.process_time_ns()
    rendered = render_session_report_json(project_session_report(session))
    render_wall_ns = time.perf_counter_ns() - wall_start
    render_cpu_ns = time.process_time_ns() - cpu_start

    total_wall_ns = time.perf_counter_ns() - total_wall_start
    total_cpu_ns = time.process_time_ns() - total_cpu_start
    measured_peak_rss = peak_rss_bytes()
    measured_current_rss = current_rss_bytes()

    expected_timeline = manifest["counts"]["normalized_timeline_entries"]
    if len(session.timeline) != expected_timeline:
        raise RuntimeError(
            "normalized timeline count does not match deterministic dataset manifest: "
            f"expected={expected_timeline} actual={len(session.timeline)}"
        )
    if not session.is_complete or not session.is_compatible:
        raise RuntimeError("benchmark dataset did not produce a complete compatible session")

    report_payload: object = json.loads(rendered)
    if not isinstance(report_payload, dict):
        raise RuntimeError("rendered benchmark report is not a JSON object")
    summary = report_payload.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError("rendered benchmark report has no summary object")
    if summary.get("timeline_entries_total") != expected_timeline:
        raise RuntimeError("rendered report timeline total does not match deterministic input")

    phase_wall_sum = load_wall_ns + normalize_wall_ns + render_wall_ns
    phase_cpu_sum = load_cpu_ns + normalize_cpu_ns + render_cpu_ns
    return {
        "current_rss_bytes": measured_current_rss,
        "diagnostics_total": len(session.diagnostics),
        "peak_rss_bytes": measured_peak_rss,
        "phases": {
            "load_parse": _phase_document(load_wall_ns, load_cpu_ns),
            "normalize_correlate": _phase_document(normalize_wall_ns, normalize_cpu_ns),
            "render_serialize": _phase_document(render_wall_ns, render_cpu_ns),
            "total": _phase_document(total_wall_ns, total_cpu_ns),
        },
        "reconciliation": {
            "cpu_seconds": (total_cpu_ns - phase_cpu_sum) / 1_000_000_000.0,
            "wall_seconds": (total_wall_ns - phase_wall_sum) / 1_000_000_000.0,
        },
        "report_bytes": len(rendered.encode("utf-8")),
        "success": True,
        "timeline_entries": len(session.timeline),
    }


def _worker(dataset_root: Path) -> int:
    try:
        document = _run_sample(dataset_root)
    except Exception as exc:
        document = {
            "error_message": str(exc),
            "error_type": type(exc).__name__,
            "success": False,
        }
        print(json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
        return 1
    print(json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    return 0


def _sample_subprocess(dataset_root: Path) -> tuple[int, JsonObject]:
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "_sample", str(dataset_root)],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        payload: object = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {
            "error_message": result.stderr.strip() or "benchmark worker emitted invalid JSON",
            "error_type": "WorkerProtocolError",
            "success": False,
        }
    if not isinstance(payload, dict):
        payload = {
            "error_message": "benchmark worker did not emit a JSON object",
            "error_type": "WorkerProtocolError",
            "success": False,
        }
    document = cast(JsonObject, payload)
    document["return_code"] = result.returncode
    if result.stderr.strip():
        document["worker_stderr"] = result.stderr.strip()
    return result.returncode, document


def _successful_samples(samples: Sequence[JsonObject], *, warmup: bool) -> list[JsonObject]:
    return [
        sample
        for sample in samples
        if sample.get("warmup") is warmup and sample.get("success") is True
    ]


def _numeric_summary(values: Sequence[float]) -> JsonObject:
    if not values:
        return {}
    return {
        "maximum": max(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "minimum": min(values),
    }


def _aggregate_samples(samples: Sequence[JsonObject]) -> JsonObject:
    measured = _successful_samples(samples, warmup=False)
    phase_names = ("load_parse", "normalize_correlate", "render_serialize", "total")
    phase_aggregates: JsonObject = {}
    for phase_name in phase_names:
        wall_values: list[float] = []
        cpu_values: list[float] = []
        for sample in measured:
            phases = sample.get("phases")
            if not isinstance(phases, Mapping):
                continue
            phase = phases.get(phase_name)
            if not isinstance(phase, Mapping):
                continue
            wall = phase.get("wall_seconds")
            cpu = phase.get("cpu_seconds")
            if isinstance(wall, int | float) and not isinstance(wall, bool):
                wall_values.append(float(wall))
            if isinstance(cpu, int | float) and not isinstance(cpu, bool):
                cpu_values.append(float(cpu))
        phase_aggregates[phase_name] = {
            "cpu_seconds": _numeric_summary(cpu_values),
            "wall_seconds": _numeric_summary(wall_values),
        }

    peak_values = [
        int(value)
        for sample in measured
        if isinstance((value := sample.get("peak_rss_bytes")), int) and not isinstance(value, bool)
    ]
    report_sizes = [
        int(value)
        for sample in measured
        if isinstance((value := sample.get("report_bytes")), int) and not isinstance(value, bool)
    ]
    failed_measured = sum(
        sample.get("warmup") is False and sample.get("success") is not True for sample in samples
    )
    failed_warmups = sum(
        sample.get("warmup") is True and sample.get("success") is not True for sample in samples
    )
    return {
        "failed_measured_samples": failed_measured,
        "failed_warmups": failed_warmups,
        "measured_samples_succeeded": len(measured),
        "peak_rss_bytes": _numeric_summary([float(value) for value in peak_values]),
        "phases": phase_aggregates,
        "report_bytes": _numeric_summary([float(value) for value in report_sizes]),
    }


def _benchmark_scale(
    scale_name: str,
    *,
    samples: int,
    warmups: int,
    workspace: Path,
) -> JsonObject:
    scale = dataset_scale(scale_name)
    dataset_root = workspace / scale.name
    manifest = write_dataset(dataset_root, scale)
    sample_documents: list[JsonObject] = []
    total_attempts = warmups + samples
    for attempt in range(total_attempts):
        _, sample = _sample_subprocess(dataset_root)
        sample["sample_index"] = attempt if attempt < warmups else attempt - warmups
        sample["warmup"] = attempt < warmups
        sample_documents.append(sample)

    return {
        "aggregates": _aggregate_samples(sample_documents),
        "dataset": manifest,
        "samples": sample_documents,
        "scale": scale.name,
    }


def _measurement_document(*, samples: int, warmups: int) -> JsonObject:
    return {
        "aggregation": (
            "median of successful measured samples; mean, minimum, and maximum retained; "
            "warmups excluded from aggregates and failures retained in raw samples"
        ),
        "cpu_clock": "time.process_time_ns",
        "measured_samples_per_scale": samples,
        "peak_rss": {
            "api": "resource.getrusage(RUSAGE_SELF).ru_maxrss",
            "linux_source_unit": "KiB",
            "macos_source_unit": "bytes",
            "normalized_unit": "bytes",
        },
        "sample_isolation": "one fresh Python subprocess per warmup or measured sample",
        "wall_clock": "time.perf_counter_ns",
        "warmups_per_scale": warmups,
    }


def _benchmark_document(
    scales: Sequence[str],
    *,
    samples: int,
    warmups: int,
    workspace: Path,
) -> JsonObject:
    runs = [
        _benchmark_scale(scale, samples=samples, warmups=warmups, workspace=workspace)
        for scale in scales
    ]
    return {
        "commit_sha": _git_commit_sha(),
        "environment": _environment_document(),
        "format": BENCHMARK_FORMAT,
        "format_version": BENCHMARK_FORMAT_VERSION,
        "measurement": _measurement_document(samples=samples, warmups=warmups),
        "report_format": "orbitops.session_report/v1",
        "runs": runs,
    }


def validate_benchmark_document(payload: object) -> None:
    """Validate the internal v1 benchmark result shape and phase reconciliation."""

    if not isinstance(payload, dict):
        raise ValueError("benchmark result must be a JSON object")
    expected_top = {
        "commit_sha",
        "environment",
        "format",
        "format_version",
        "measurement",
        "report_format",
        "runs",
    }
    if set(payload) != expected_top:
        raise ValueError("benchmark result has unexpected top-level keys")
    if payload["format"] != BENCHMARK_FORMAT:
        raise ValueError("unsupported benchmark result format")
    if payload["format_version"] != BENCHMARK_FORMAT_VERSION:
        raise ValueError("unsupported benchmark result version")
    commit_sha = payload["commit_sha"]
    if not isinstance(commit_sha, str) or len(commit_sha) != 40:
        raise ValueError("benchmark result commit_sha must contain a full Git SHA")
    if payload["report_format"] != "orbitops.session_report/v1":
        raise ValueError("benchmark result has an unexpected report format")

    runs = payload["runs"]
    if not isinstance(runs, list) or not runs:
        raise ValueError("benchmark result must contain at least one run")
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError("benchmark run must be a JSON object")
        if set(run) != {"aggregates", "dataset", "samples", "scale"}:
            raise ValueError("benchmark run has unexpected keys")
        dataset = run["dataset"]
        if not isinstance(dataset, dict):
            raise ValueError("benchmark run dataset must be an object")
        if dataset.get("format") != DATASET_FORMAT:
            raise ValueError("benchmark run has an unexpected dataset format")
        if dataset.get("format_version") != DATASET_FORMAT_VERSION:
            raise ValueError("benchmark run has an unexpected dataset version")
        samples_payload = run["samples"]
        if not isinstance(samples_payload, list) or not samples_payload:
            raise ValueError("benchmark run must retain raw samples")
        for sample in samples_payload:
            if not isinstance(sample, dict):
                raise ValueError("benchmark sample must be a JSON object")
            if sample.get("success") is not True:
                continue
            phases = sample.get("phases")
            reconciliation = sample.get("reconciliation")
            if not isinstance(phases, dict) or not isinstance(reconciliation, dict):
                raise ValueError("successful benchmark sample is missing timing data")
            if set(phases) != {"load_parse", "normalize_correlate", "render_serialize", "total"}:
                raise ValueError("successful benchmark sample has unexpected phases")
            for field in ("wall_seconds", "cpu_seconds"):
                gap = reconciliation.get(field)
                if not isinstance(gap, int | float) or isinstance(gap, bool) or gap < 0.0:
                    raise ValueError("benchmark phase timings do not reconcile inside total timing")


def _write_result(path: Path, document: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _benchmark_command(args: argparse.Namespace) -> int:
    scales = cast(list[str], args.scales)
    samples = cast(int, args.samples)
    warmups = cast(int, args.warmups)
    output = cast(Path, args.output)
    with tempfile.TemporaryDirectory(prefix="orbitops-session-benchmark-") as directory_name:
        document = _benchmark_document(
            scales,
            samples=samples,
            warmups=warmups,
            workspace=Path(directory_name),
        )
    validate_benchmark_document(document)
    _write_result(output, document)

    failures = 0
    for run in cast(list[JsonObject], document["runs"]):
        aggregates = cast(JsonObject, run["aggregates"])
        failures += cast(int, aggregates["failed_measured_samples"])
        failures += cast(int, aggregates["failed_warmups"])
    print(
        "session inspection benchmark complete: "
        f"scales={','.join(scales)} samples={samples} warmups={warmups} failures={failures} "
        f"output={output}"
    )
    return 0 if failures == 0 else 1


def _generate_command(args: argparse.Namespace) -> int:
    scale = dataset_scale(cast(str, args.scale))
    output_dir = cast(Path, args.output_dir)
    manifest = write_dataset(output_dir, scale)
    print(
        "session benchmark dataset generated: "
        f"scale={scale.name} records={manifest['counts']['input_records_total']} "
        f"timeline={manifest['counts']['normalized_timeline_entries']} output={output_dir}"
    )
    return 0


def _smoke_command() -> int:
    with tempfile.TemporaryDirectory(prefix="orbitops-session-benchmark-smoke-") as directory_name:
        workspace = Path(directory_name)
        scale = smoke_scale()
        dataset_root = workspace / scale.name
        manifest = write_dataset(dataset_root, scale)
        return_code, sample = _sample_subprocess(dataset_root)
    if return_code != 0 or sample.get("success") is not True:
        raise RuntimeError(f"session benchmark smoke sample failed: {sample}")
    print(
        "session inspection benchmark smoke ok: "
        f"records={manifest['counts']['input_records_total']} "
        f"timeline={manifest['counts']['normalized_timeline_entries']} "
        f"report_bytes={sample['report_bytes']}"
    )
    return 0


def _validate_command(args: argparse.Namespace) -> int:
    path = cast(Path, args.path)
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    validate_benchmark_document(payload)
    print(f"session inspection benchmark result valid: {path}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="generate one deterministic dataset")
    generate.add_argument("--scale", choices=sorted(DATASET_SCALES), required=True)
    generate.add_argument("--output-dir", type=Path, required=True)

    benchmark = subparsers.add_parser("benchmark", help="run isolated benchmark samples")
    benchmark.add_argument(
        "--scales",
        nargs="+",
        choices=sorted(DATASET_SCALES),
        default=sorted(DATASET_SCALES),
    )
    benchmark.add_argument("--samples", type=_positive_int, default=5)
    benchmark.add_argument("--warmups", type=_non_negative_int, default=1)
    benchmark.add_argument("--output", type=Path, required=True)

    subparsers.add_parser("smoke", help="run one bounded functional benchmark sample")

    validate = subparsers.add_parser("validate", help="validate a raw benchmark result")
    validate.add_argument("path", type=Path)

    worker = subparsers.add_parser("_sample", help=argparse.SUPPRESS)
    worker.add_argument("dataset_root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    command = cast(str, args.command)
    if command == "generate":
        return _generate_command(args)
    if command == "benchmark":
        return _benchmark_command(args)
    if command == "smoke":
        return _smoke_command()
    if command == "validate":
        return _validate_command(args)
    if command == "_sample":
        return _worker(cast(Path, args.dataset_root))
    raise AssertionError(f"unhandled command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run and validate long-lived deterministic session-inspection soak evidence."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypeAlias, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.session import inspect_session  # noqa: E402
from orbitops.session.reporting import (  # noqa: E402
    REPORT_FORMAT,
    REPORT_FORMAT_VERSION,
    project_session_report,
    render_session_report_json,
)
from session_benchmark_support import (  # noqa: E402
    DATASET_FORMAT,
    DATASET_FORMAT_VERSION,
    DATASET_SCALES,
    DatasetManifest,
    DatasetPaths,
    DatasetScale,
    current_rss_bytes,
    dataset_scale,
    peak_rss_bytes,
    smoke_scale,
    verify_dataset_files,
    write_dataset,
)

SOAK_FORMAT = "orbitops.session_inspection_soak"
SOAK_FORMAT_VERSION = 1
REFERENCE_SOAK_MINIMUM_SECONDS = 60.0 * 60.0
JsonObject: TypeAlias = dict[str, object]


def _non_negative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.0:
        raise argparse.ArgumentTypeError("must be finite and non-negative")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise argparse.ArgumentTypeError("must be finite and positive")
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
        raise RuntimeError("soak requires a Git checkout with a resolvable HEAD commit")
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


def _numeric(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be finite")
    return numeric


def _non_negative_number(value: object, name: str) -> float:
    numeric = _numeric(value, name)
    if numeric < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return numeric


def _validate_final_report(
    payload: object,
    manifest: DatasetManifest,
    *,
    report_bytes: int,
) -> JsonObject:
    if not isinstance(payload, dict):
        raise RuntimeError("rendered soak report is not a JSON object")
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise RuntimeError("rendered soak report has no metadata object")
    if metadata.get("report_format") != REPORT_FORMAT:
        raise RuntimeError("rendered soak report has an unexpected report format")
    if metadata.get("report_format_version") != REPORT_FORMAT_VERSION:
        raise RuntimeError("rendered soak report has an unexpected report version")

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError("rendered soak report has no summary object")
    expected_timeline = manifest["counts"]["normalized_timeline_entries"]
    if summary.get("complete") is not True or summary.get("compatible") is not True:
        raise RuntimeError("soak dataset did not produce a complete compatible report")
    if summary.get("source_count") != 3:
        raise RuntimeError("soak report did not retain all three evidence sources")
    if summary.get("timeline_entries_total") != expected_timeline:
        raise RuntimeError("soak report timeline total does not match deterministic input")
    if summary.get("timeline_entries_rendered") != expected_timeline:
        raise RuntimeError("soak report unexpectedly truncated deterministic input")

    sources = payload.get("sources")
    if not isinstance(sources, list) or len(sources) != 3:
        raise RuntimeError("soak report must contain exactly three source summaries")
    by_lane: dict[str, Mapping[str, object]] = {}
    for source in sources:
        if not isinstance(source, Mapping):
            raise RuntimeError("soak report source summary must be an object")
        lane = source.get("lane")
        if not isinstance(lane, str) or lane in by_lane:
            raise RuntimeError("soak report source lanes must be unique strings")
        by_lane[lane] = source
    if set(by_lane) != {"telemetry", "alarm", "link"}:
        raise RuntimeError("soak report source lanes do not match deterministic input")

    expected_records = {
        "telemetry": manifest["counts"]["telemetry_records"],
        "alarm": manifest["counts"]["alarm_events"],
        "link": manifest["counts"]["link_events"],
    }
    for lane, expected in expected_records.items():
        if by_lane[lane].get("record_count") != expected:
            raise RuntimeError(f"soak report {lane} record count does not match manifest")
    if by_lane["alarm"].get("summary_present") is not True:
        raise RuntimeError("soak alarm lane is missing its final run summary")
    if by_lane["link"].get("summary_present") is not True:
        raise RuntimeError("soak link lane is missing its final run summary")

    alarm_counters = by_lane["alarm"].get("counters")
    link_counters = by_lane["link"].get("counters")
    if not isinstance(alarm_counters, Mapping) or not isinstance(link_counters, Mapping):
        raise RuntimeError("soak report source counters are missing")
    if alarm_counters.get("transitions_total") != manifest["counts"]["alarm_transitions"]:
        raise RuntimeError("soak alarm final summary does not match deterministic transitions")
    packet_count = manifest["parameters"]["packet_count"]
    for counter in ("packets_received", "deliveries_scheduled", "deliveries_forwarded"):
        if link_counters.get(counter) != packet_count:
            raise RuntimeError(f"soak link final summary counter {counter} is inconsistent")

    observed_input_records = sum(expected_records.values())
    if observed_input_records != manifest["counts"]["input_records_total"]:
        raise RuntimeError("soak manifest input record total does not reconcile")
    diagnostics_total = summary.get("diagnostics_total")
    if isinstance(diagnostics_total, bool) or not isinstance(diagnostics_total, int):
        raise RuntimeError("soak report diagnostics total is invalid")
    return {
        "compatible": True,
        "complete": True,
        "diagnostics_total": diagnostics_total,
        "input_records_total": observed_input_records,
        "report_bytes": report_bytes,
        "source_count": 3,
        "timeline_entries_total": expected_timeline,
    }


def _inspection_cycle(paths: DatasetPaths, manifest: DatasetManifest) -> JsonObject:
    session = inspect_session(
        telemetry_path=paths.telemetry,
        link_events_path=paths.link_events,
        alarm_events_path=paths.alarm_events,
    )
    rendered = render_session_report_json(project_session_report(session))
    report_bytes = len(rendered.encode("utf-8"))
    try:
        payload: object = json.loads(rendered)
    except json.JSONDecodeError as exc:
        raise RuntimeError("rendered soak report is not valid JSON") from exc
    return _validate_final_report(payload, manifest, report_bytes=report_bytes)


def _resource_sample(elapsed_seconds: float, iterations_completed: int) -> JsonObject:
    return {
        "current_rss_bytes": current_rss_bytes(),
        "elapsed_seconds": elapsed_seconds,
        "iterations_completed": iterations_completed,
        "peak_rss_bytes": peak_rss_bytes(),
    }


def _resource_summary(samples: Sequence[JsonObject]) -> JsonObject:
    current_values = [
        value
        for sample in samples
        if isinstance((value := sample.get("current_rss_bytes")), int)
        and not isinstance(value, bool)
    ]
    peak_values = [
        value
        for sample in samples
        if isinstance((value := sample.get("peak_rss_bytes")), int) and not isinstance(value, bool)
    ]
    initial_current = current_values[0] if current_values else None
    final_current = current_values[-1] if current_values else None
    current_delta = (
        final_current - initial_current
        if initial_current is not None and final_current is not None
        else None
    )
    return {
        "current_rss_bytes_delta": current_delta,
        "current_rss_bytes_final": final_current,
        "current_rss_bytes_initial": initial_current,
        "current_rss_bytes_maximum": max(current_values) if current_values else None,
        "peak_rss_bytes_maximum": max(peak_values) if peak_values else None,
    }


def _soak_document(
    scale: DatasetScale,
    *,
    duration_seconds: float,
    iteration_interval_seconds: float,
    resource_sample_interval_seconds: float,
    workspace: Path,
) -> JsonObject:
    dataset_root = workspace / scale.name
    manifest = write_dataset(dataset_root, scale)
    paths = verify_dataset_files(dataset_root, manifest)

    start_wall = time.perf_counter()
    start_cpu = time.process_time()
    resource_samples: list[JsonObject] = []
    iterations: list[JsonObject] = []
    next_resource_sample: float | None = None
    next_iteration_start = start_wall
    last_summary: JsonObject | None = None

    while True:
        iteration_index = len(iterations)
        iteration_start = time.perf_counter()
        try:
            last_summary = _inspection_cycle(paths, manifest)
        except Exception as exc:
            iteration_elapsed = time.perf_counter() - iteration_start
            elapsed = time.perf_counter() - start_wall
            iterations.append(
                {
                    "elapsed_seconds": elapsed,
                    "error_message": str(exc),
                    "error_type": type(exc).__name__,
                    "iteration_index": iteration_index,
                    "success": False,
                    "wall_seconds": iteration_elapsed,
                }
            )
            break

        iteration_elapsed = time.perf_counter() - iteration_start
        elapsed = time.perf_counter() - start_wall
        iterations.append(
            {
                "elapsed_seconds": elapsed,
                "iteration_index": iteration_index,
                "success": True,
                "wall_seconds": iteration_elapsed,
            }
        )

        if next_resource_sample is None:
            resource_samples.append(_resource_sample(elapsed, len(iterations)))
            next_resource_sample = elapsed + resource_sample_interval_seconds
        elif elapsed >= next_resource_sample:
            resource_samples.append(_resource_sample(elapsed, len(iterations)))
            while next_resource_sample <= elapsed:
                next_resource_sample += resource_sample_interval_seconds

        if elapsed >= duration_seconds:
            break

        next_iteration_start += iteration_interval_seconds
        remaining = next_iteration_start - time.perf_counter()
        if remaining > 0.0:
            time.sleep(remaining)

    elapsed_seconds = time.perf_counter() - start_wall
    cpu_seconds = time.process_time() - start_cpu
    if (
        not resource_samples
        or resource_samples[-1].get("iterations_completed") != len(iterations)
        or cast(float, resource_samples[-1]["elapsed_seconds"]) < elapsed_seconds
    ):
        resource_samples.append(_resource_sample(elapsed_seconds, len(iterations)))

    failed_iterations = sum(item.get("success") is not True for item in iterations)
    successful_iterations = len(iterations) - failed_iterations
    duration_met = elapsed_seconds >= duration_seconds
    success = (
        failed_iterations == 0
        and successful_iterations > 0
        and duration_met
        and last_summary is not None
    )
    reference_criteria_met = success and elapsed_seconds >= REFERENCE_SOAK_MINIMUM_SECONDS
    document: JsonObject = {
        "commit_sha": _git_commit_sha(),
        "dataset": manifest,
        "environment": _environment_document(),
        "final_summary": last_summary if success else None,
        "format": SOAK_FORMAT,
        "format_version": SOAK_FORMAT_VERSION,
        "iterations": iterations,
        "parameters": {
            "duration_seconds_requested": duration_seconds,
            "iteration_interval_seconds": iteration_interval_seconds,
            "resource_sample_interval_seconds": resource_sample_interval_seconds,
            "scale": scale.name,
        },
        "report_format": f"{REPORT_FORMAT}/v{REPORT_FORMAT_VERSION}",
        "resource_samples": resource_samples,
        "resource_summary": _resource_summary(resource_samples),
        "summary": {
            "cpu_seconds": cpu_seconds,
            "duration_met": duration_met,
            "elapsed_seconds": elapsed_seconds,
            "failed_iterations": failed_iterations,
            "iterations_attempted": len(iterations),
            "iterations_succeeded": successful_iterations,
            "reference_soak_criteria_met": reference_criteria_met,
            "reference_soak_minimum_seconds": REFERENCE_SOAK_MINIMUM_SECONDS,
            "success": success,
        },
    }
    return document


def _validate_resource_value(value: object, name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer or null")


def validate_soak_document(payload: object) -> None:
    """Validate the internal v1 soak result shape and final-summary reconciliation."""

    if not isinstance(payload, dict):
        raise ValueError("soak result must be a JSON object")
    expected_top = {
        "commit_sha",
        "dataset",
        "environment",
        "final_summary",
        "format",
        "format_version",
        "iterations",
        "parameters",
        "report_format",
        "resource_samples",
        "resource_summary",
        "summary",
    }
    if set(payload) != expected_top:
        raise ValueError("soak result has unexpected top-level keys")
    if payload["format"] != SOAK_FORMAT:
        raise ValueError("unsupported soak result format")
    if payload["format_version"] != SOAK_FORMAT_VERSION:
        raise ValueError("unsupported soak result version")
    commit_sha = payload["commit_sha"]
    if not isinstance(commit_sha, str) or len(commit_sha) != 40:
        raise ValueError("soak result commit_sha must contain a full Git SHA")
    if payload["report_format"] != f"{REPORT_FORMAT}/v{REPORT_FORMAT_VERSION}":
        raise ValueError("soak result has an unexpected report format")

    dataset = payload["dataset"]
    if not isinstance(dataset, dict):
        raise ValueError("soak result dataset must be an object")
    if dataset.get("format") != DATASET_FORMAT:
        raise ValueError("soak result has an unexpected dataset format")
    if dataset.get("format_version") != DATASET_FORMAT_VERSION:
        raise ValueError("soak result has an unexpected dataset version")

    parameters = payload["parameters"]
    if not isinstance(parameters, dict):
        raise ValueError("soak result parameters must be an object")
    expected_parameters = {
        "duration_seconds_requested",
        "iteration_interval_seconds",
        "resource_sample_interval_seconds",
        "scale",
    }
    if set(parameters) != expected_parameters:
        raise ValueError("soak result has unexpected parameters")
    requested_duration = _non_negative_number(
        parameters["duration_seconds_requested"], "duration_seconds_requested"
    )
    _non_negative_number(parameters["iteration_interval_seconds"], "iteration_interval_seconds")
    if (
        _non_negative_number(
            parameters["resource_sample_interval_seconds"], "resource_sample_interval_seconds"
        )
        <= 0.0
    ):
        raise ValueError("resource_sample_interval_seconds must be positive")
    if parameters["scale"] != dataset.get("scale"):
        raise ValueError("soak result scale does not match dataset manifest")

    iterations = payload["iterations"]
    if not isinstance(iterations, list) or not iterations:
        raise ValueError("soak result must retain at least one iteration")
    failed_iterations = 0
    for expected_index, iteration in enumerate(iterations):
        if not isinstance(iteration, dict):
            raise ValueError("soak iteration must be a JSON object")
        if iteration.get("iteration_index") != expected_index:
            raise ValueError("soak iteration indices must be contiguous")
        _non_negative_number(iteration.get("elapsed_seconds"), "iteration elapsed_seconds")
        _non_negative_number(iteration.get("wall_seconds"), "iteration wall_seconds")
        success = iteration.get("success")
        if not isinstance(success, bool):
            raise ValueError("soak iteration success must be boolean")
        if not success:
            failed_iterations += 1
            if not isinstance(iteration.get("error_type"), str) or not isinstance(
                iteration.get("error_message"), str
            ):
                raise ValueError("failed soak iteration must retain its error")

    resource_samples = payload["resource_samples"]
    if not isinstance(resource_samples, list) or not resource_samples:
        raise ValueError("soak result must retain resource samples")
    previous_elapsed = -1.0
    previous_iterations = -1
    for sample in resource_samples:
        if not isinstance(sample, dict):
            raise ValueError("soak resource sample must be a JSON object")
        if set(sample) != {
            "current_rss_bytes",
            "elapsed_seconds",
            "iterations_completed",
            "peak_rss_bytes",
        }:
            raise ValueError("soak resource sample has unexpected keys")
        elapsed = _non_negative_number(sample["elapsed_seconds"], "resource elapsed_seconds")
        if elapsed < previous_elapsed:
            raise ValueError("soak resource samples must use monotonic elapsed time")
        completed = sample["iterations_completed"]
        if isinstance(completed, bool) or not isinstance(completed, int) or completed < 0:
            raise ValueError("resource iterations_completed must be a non-negative integer")
        if completed < previous_iterations or completed > len(iterations):
            raise ValueError("resource sample iteration count is inconsistent")
        _validate_resource_value(sample["current_rss_bytes"], "current_rss_bytes")
        _validate_resource_value(sample["peak_rss_bytes"], "peak_rss_bytes")
        previous_elapsed = elapsed
        previous_iterations = completed

    resource_summary = payload["resource_summary"]
    if not isinstance(resource_summary, dict):
        raise ValueError("soak result resource_summary must be an object")
    expected_resource_summary = {
        "current_rss_bytes_delta",
        "current_rss_bytes_final",
        "current_rss_bytes_initial",
        "current_rss_bytes_maximum",
        "peak_rss_bytes_maximum",
    }
    if set(resource_summary) != expected_resource_summary:
        raise ValueError("soak resource summary has unexpected keys")
    for name in expected_resource_summary - {"current_rss_bytes_delta"}:
        _validate_resource_value(resource_summary[name], name)
    delta = resource_summary["current_rss_bytes_delta"]
    if delta is not None and (isinstance(delta, bool) or not isinstance(delta, int)):
        raise ValueError("current_rss_bytes_delta must be an integer or null")
    initial = resource_summary["current_rss_bytes_initial"]
    final = resource_summary["current_rss_bytes_final"]
    if initial is not None and final is not None:
        expected_delta = cast(int, final) - cast(int, initial)
        if delta != expected_delta:
            raise ValueError("soak current RSS delta does not reconcile")

    summary = payload["summary"]
    if not isinstance(summary, dict):
        raise ValueError("soak result summary must be an object")
    expected_summary = {
        "cpu_seconds",
        "duration_met",
        "elapsed_seconds",
        "failed_iterations",
        "iterations_attempted",
        "iterations_succeeded",
        "reference_soak_criteria_met",
        "reference_soak_minimum_seconds",
        "success",
    }
    if set(summary) != expected_summary:
        raise ValueError("soak result summary has unexpected keys")
    elapsed = _non_negative_number(summary["elapsed_seconds"], "summary elapsed_seconds")
    _non_negative_number(summary["cpu_seconds"], "summary cpu_seconds")
    if summary["iterations_attempted"] != len(iterations):
        raise ValueError("soak summary iteration count does not reconcile")
    if summary["failed_iterations"] != failed_iterations:
        raise ValueError("soak summary failed iteration count does not reconcile")
    if summary["iterations_succeeded"] != len(iterations) - failed_iterations:
        raise ValueError("soak summary successful iteration count does not reconcile")
    duration_met = summary["duration_met"]
    if not isinstance(duration_met, bool) or duration_met != (elapsed >= requested_duration):
        raise ValueError("soak summary duration state does not reconcile")
    if summary["reference_soak_minimum_seconds"] != REFERENCE_SOAK_MINIMUM_SECONDS:
        raise ValueError("soak result has an unexpected reference minimum duration")
    success = summary["success"]
    expected_success = failed_iterations == 0 and len(iterations) > 0 and duration_met
    if not isinstance(success, bool) or success != expected_success:
        raise ValueError("soak summary success state does not reconcile")
    expected_reference = success and elapsed >= REFERENCE_SOAK_MINIMUM_SECONDS
    if summary["reference_soak_criteria_met"] != expected_reference:
        raise ValueError("soak reference criteria state does not reconcile")

    final_summary = payload["final_summary"]
    if success:
        if not isinstance(final_summary, dict):
            raise ValueError("successful soak must retain a final validated summary")
        expected_final = {
            "compatible",
            "complete",
            "diagnostics_total",
            "input_records_total",
            "report_bytes",
            "source_count",
            "timeline_entries_total",
        }
        if set(final_summary) != expected_final:
            raise ValueError("soak final summary has unexpected keys")
        if final_summary["complete"] is not True or final_summary["compatible"] is not True:
            raise ValueError("soak final summary must be complete and compatible")
        if final_summary["source_count"] != 3:
            raise ValueError("soak final summary source count is inconsistent")
        counts = dataset.get("counts")
        if not isinstance(counts, dict):
            raise ValueError("soak dataset counts are missing")
        if final_summary["input_records_total"] != counts.get("input_records_total"):
            raise ValueError("soak final input count does not match dataset")
        if final_summary["timeline_entries_total"] != counts.get("normalized_timeline_entries"):
            raise ValueError("soak final timeline count does not match dataset")
        report_bytes = final_summary["report_bytes"]
        if isinstance(report_bytes, bool) or not isinstance(report_bytes, int) or report_bytes <= 0:
            raise ValueError("soak final report size must be positive")
    elif final_summary is not None:
        raise ValueError("failed soak must not claim a final validated summary")


def _write_result(path: Path, document: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run_command(args: argparse.Namespace) -> int:
    scale = dataset_scale(cast(str, args.scale))
    duration_seconds = cast(float, args.duration_seconds)
    iteration_interval_seconds = cast(float, args.iteration_interval_seconds)
    resource_sample_interval_seconds = cast(float, args.resource_sample_interval_seconds)
    output = cast(Path, args.output)
    with tempfile.TemporaryDirectory(prefix="orbitops-session-soak-") as directory_name:
        document = _soak_document(
            scale,
            duration_seconds=duration_seconds,
            iteration_interval_seconds=iteration_interval_seconds,
            resource_sample_interval_seconds=resource_sample_interval_seconds,
            workspace=Path(directory_name),
        )
    validate_soak_document(document)
    _write_result(output, document)
    summary = cast(JsonObject, document["summary"])
    print(
        "session inspection soak complete: "
        f"scale={scale.name} elapsed={cast(float, summary['elapsed_seconds']):.3f}s "
        f"iterations={summary['iterations_attempted']} failures={summary['failed_iterations']} "
        f"reference_criteria={str(summary['reference_soak_criteria_met']).lower()} output={output}"
    )
    return 0 if summary["success"] is True else 1


def _smoke_command() -> int:
    with tempfile.TemporaryDirectory(prefix="orbitops-session-soak-smoke-") as directory_name:
        document = _soak_document(
            smoke_scale(),
            duration_seconds=0.0,
            iteration_interval_seconds=0.0,
            resource_sample_interval_seconds=1.0,
            workspace=Path(directory_name),
        )
    validate_soak_document(document)
    summary = cast(JsonObject, document["summary"])
    if summary["success"] is not True:
        raise RuntimeError(f"session soak smoke failed: {summary}")
    final_summary = cast(JsonObject, document["final_summary"])
    print(
        "session inspection soak smoke ok: "
        f"iterations={summary['iterations_attempted']} "
        f"timeline={final_summary['timeline_entries_total']} "
        f"report_bytes={final_summary['report_bytes']}"
    )
    return 0


def _validate_command(args: argparse.Namespace) -> int:
    path = cast(Path, args.path)
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    validate_soak_document(payload)
    document = cast(JsonObject, payload)
    summary = cast(JsonObject, document["summary"])
    print(
        "session inspection soak result valid: "
        f"success={str(summary['success']).lower()} "
        f"reference_criteria={str(summary['reference_soak_criteria_met']).lower()} path={path}"
    )
    return 0 if summary["success"] is True else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="run a duration-based session-inspection soak")
    run.add_argument("--scale", choices=sorted(DATASET_SCALES), default="medium")
    run.add_argument("--duration-seconds", type=_non_negative_float, default=3600.0)
    run.add_argument("--iteration-interval-seconds", type=_non_negative_float, default=1.0)
    run.add_argument("--resource-sample-interval-seconds", type=_positive_float, default=60.0)
    run.add_argument("--output", type=Path, required=True)

    subparsers.add_parser("smoke", help="run one bounded functional soak cycle")

    validate = subparsers.add_parser("validate", help="validate a raw soak result")
    validate.add_argument("path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    command = cast(str, args.command)
    if command == "run":
        return _run_command(args)
    if command == "smoke":
        return _smoke_command()
    if command == "validate":
        return _validate_command(args)
    raise AssertionError(f"unhandled command: {command}")


if __name__ == "__main__":
    sys.exit(main())

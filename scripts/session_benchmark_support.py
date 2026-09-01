#!/usr/bin/env python3
"""Deterministic evidence generation and measurement helpers for session benchmarks."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import resource
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

from orbitops.alarm_events import (
    AlarmEvent,
    AlarmEventType,
    AlarmRunMetadata,
    AlarmRunStatistics,
)
from orbitops.link.events import LinkEvent, LinkEventType, LinkRunMetadata
from orbitops.link.statistics import LinkStatistics
from orbitops.protocol import Mode, TelemetryPacket, encode_packet
from orbitops.recorder import SessionRecorder

DATASET_FORMAT = "orbitops.session_benchmark_dataset"
DATASET_FORMAT_VERSION = 1
LINK_EVENTS_PER_PACKET = 3


@dataclass(frozen=True, slots=True)
class DatasetScale:
    """Named deterministic dataset parameters."""

    name: str
    packet_count: int
    alarm_stride: int


DATASET_SCALES: Mapping[str, DatasetScale] = {
    "small": DatasetScale("small", packet_count=250, alarm_stride=25),
    "medium": DatasetScale("medium", packet_count=2_500, alarm_stride=25),
    "large": DatasetScale("large", packet_count=10_000, alarm_stride=25),
}
_SMOKE_SCALE = DatasetScale("smoke", packet_count=64, alarm_stride=16)


class DatasetParameters(TypedDict):
    packet_count: int
    alarm_stride: int
    link_events_per_packet: int


class DatasetCounts(TypedDict):
    telemetry_records: int
    alarm_events: int
    alarm_transitions: int
    link_events: int
    input_records_total: int
    normalized_timeline_entries: int


class DatasetFiles(TypedDict):
    telemetry: str
    alarm_events: str
    link_events: str


class DatasetDigests(TypedDict):
    telemetry_sha256: str
    alarm_events_sha256: str
    link_events_sha256: str


class DatasetManifest(TypedDict):
    format: str
    format_version: int
    scale: str
    parameters: DatasetParameters
    counts: DatasetCounts
    files: DatasetFiles
    sha256: DatasetDigests


@dataclass(frozen=True, slots=True)
class DatasetPaths:
    root: Path
    manifest: Path
    telemetry: Path
    alarm_events: Path
    link_events: Path


def dataset_scale(name: str) -> DatasetScale:
    """Return one documented dataset preset."""

    try:
        return DATASET_SCALES[name]
    except KeyError as exc:
        choices = ", ".join(sorted(DATASET_SCALES))
        raise ValueError(f"dataset scale must be one of: {choices}") from exc


def smoke_scale() -> DatasetScale:
    """Return the tightly bounded CI-only dataset preset."""

    return _SMOKE_SCALE


def dataset_paths(root: Path) -> DatasetPaths:
    """Return canonical paths for one generated dataset directory."""

    if not isinstance(root, Path):
        raise TypeError("root must be a pathlib.Path")
    return DatasetPaths(
        root=root,
        manifest=root / "dataset.json",
        telemetry=root / "telemetry.jsonl",
        alarm_events=root / "alarm-events.jsonl",
        link_events=root / "link-events.jsonl",
    )


def _write_jsonl(path: Path, documents: Iterable[Mapping[str, object]]) -> None:
    path.write_text(
        "".join(
            json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
            for document in documents
        ),
        encoding="utf-8",
    )


def _write_telemetry(path: Path, packet_count: int) -> None:
    with SessionRecorder(path) as recorder:
        for sequence in range(packet_count):
            packet = TelemetryPacket(
                sequence=sequence,
                timestamp_ms=sequence * 100,
                mode=Mode.NOMINAL,
                battery_mv=8200 - (sequence % 200),
                bus_current_ma=240 + (sequence % 40),
                temperature_centi_c=2100 + (sequence % 500),
                roll_centi_deg=(sequence % 401) - 200,
                pitch_centi_deg=200 - (sequence % 401),
                yaw_centi_deg=((sequence * 7) % 60001) - 30000,
            )
            recorder.write(encode_packet(packet), 1_000.0 + sequence / 10.0)


def _alarm_events(packet_count: int, alarm_stride: int) -> tuple[AlarmEvent, ...]:
    metadata = AlarmRunMetadata(
        policy_name="benchmark",
        policy_reference="benchmark:v1",
        policy_schema_version=1,
        policy_fingerprint="sha256:" + "1" * 64,
    )
    events: list[AlarmEvent] = [
        AlarmEvent(
            session_id="session-benchmark-alarm",
            event_index=0,
            elapsed_ns=0,
            event_type=AlarmEventType.RUN_METADATA,
            attributes=metadata.to_attributes(),
        )
    ]
    for sequence in range(alarm_stride - 1, packet_count, alarm_stride):
        event_index = len(events)
        events.append(
            AlarmEvent(
                session_id="session-benchmark-alarm",
                event_index=event_index,
                elapsed_ns=event_index * 1_000_000,
                event_type=AlarmEventType.ALARM_RAISED,
                packet_sequence=sequence,
                attributes={
                    "alarm_identity": "benchmark_temperature",
                    "code": "BENCHMARK_TEMP",
                    "message": "deterministic benchmark transition",
                    "observed_value": 50.0 + (sequence % 10),
                    "severity": "warning",
                    "threshold": 50.0,
                },
            )
        )

    transition_count = len(events) - 1
    event_index = len(events)
    events.append(
        AlarmEvent(
            session_id="session-benchmark-alarm",
            event_index=event_index,
            elapsed_ns=event_index * 1_000_000,
            event_type=AlarmEventType.RUN_SUMMARY,
            attributes=AlarmRunStatistics(transitions_raised=transition_count).to_attributes(),
        )
    )
    return tuple(events)


def _link_events(packet_count: int) -> tuple[LinkEvent, ...]:
    metadata = LinkRunMetadata(
        configuration_fingerprint="sha256:" + "2" * 64,
        profile_name="benchmark",
        profile_reference="benchmark:v1",
        profile_schema_version=1,
    )
    events: list[LinkEvent] = [
        LinkEvent(
            session_id="session-benchmark-link",
            event_index=0,
            elapsed_ns=0,
            event_type=LinkEventType.RUN_METADATA,
            attributes=metadata.to_attributes(),
        )
    ]
    operational_types = (
        LinkEventType.PACKET_RECEIVED,
        LinkEventType.DELIVERY_SCHEDULED,
        LinkEventType.PACKET_FORWARDED,
    )
    for packet_index in range(packet_count):
        for event_type in operational_types:
            event_index = len(events)
            events.append(
                LinkEvent(
                    session_id="session-benchmark-link",
                    event_index=event_index,
                    elapsed_ns=event_index * 1_000_000,
                    event_type=event_type,
                    packet_index=packet_index,
                )
            )

    event_index = len(events)
    events.append(
        LinkEvent(
            session_id="session-benchmark-link",
            event_index=event_index,
            elapsed_ns=event_index * 1_000_000,
            event_type=LinkEventType.RUN_SUMMARY,
            attributes=LinkStatistics(
                packets_received=packet_count,
                deliveries_scheduled=packet_count,
                deliveries_forwarded=packet_count,
            ).to_dict(),
        )
    )
    return tuple(events)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_dataset(root: Path, scale: DatasetScale) -> DatasetManifest:
    """Generate one deterministic complete three-lane benchmark dataset."""

    if not isinstance(root, Path):
        raise TypeError("root must be a pathlib.Path")
    if not isinstance(scale, DatasetScale):
        raise TypeError("scale must be a DatasetScale")
    if scale.packet_count <= 0:
        raise ValueError("packet_count must be positive")
    if not 1 <= scale.alarm_stride <= scale.packet_count:
        raise ValueError("alarm_stride must be between one and packet_count")

    paths = dataset_paths(root)
    root.mkdir(parents=True, exist_ok=True)
    _write_telemetry(paths.telemetry, scale.packet_count)
    alarm_events = _alarm_events(scale.packet_count, scale.alarm_stride)
    _write_jsonl(paths.alarm_events, (event.to_dict() for event in alarm_events))
    link_events = _link_events(scale.packet_count)
    _write_jsonl(paths.link_events, (event.to_dict() for event in link_events))

    alarm_transitions = len(alarm_events) - 2
    counts = DatasetCounts(
        telemetry_records=scale.packet_count,
        alarm_events=len(alarm_events),
        alarm_transitions=alarm_transitions,
        link_events=len(link_events),
        input_records_total=scale.packet_count + len(alarm_events) + len(link_events),
        normalized_timeline_entries=(
            scale.packet_count + alarm_transitions + scale.packet_count * LINK_EVENTS_PER_PACKET
        ),
    )
    manifest = DatasetManifest(
        format=DATASET_FORMAT,
        format_version=DATASET_FORMAT_VERSION,
        scale=scale.name,
        parameters=DatasetParameters(
            packet_count=scale.packet_count,
            alarm_stride=scale.alarm_stride,
            link_events_per_packet=LINK_EVENTS_PER_PACKET,
        ),
        counts=counts,
        files=DatasetFiles(
            telemetry=paths.telemetry.name,
            alarm_events=paths.alarm_events.name,
            link_events=paths.link_events.name,
        ),
        sha256=DatasetDigests(
            telemetry_sha256=_sha256(paths.telemetry),
            alarm_events_sha256=_sha256(paths.alarm_events),
            link_events_sha256=_sha256(paths.link_events),
        ),
    )
    paths.manifest.write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def load_dataset_manifest(root: Path) -> DatasetManifest:
    """Load and minimally validate one generated dataset manifest."""

    paths = dataset_paths(root)
    payload: object = json.loads(paths.manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("dataset manifest must be a JSON object")
    if payload.get("format") != DATASET_FORMAT:
        raise ValueError("unsupported dataset manifest format")
    if payload.get("format_version") != DATASET_FORMAT_VERSION:
        raise ValueError("unsupported dataset manifest version")
    return cast(DatasetManifest, payload)


def verify_dataset_files(root: Path, manifest: DatasetManifest) -> DatasetPaths:
    """Verify evidence filenames and digests before one benchmark sample."""

    paths = dataset_paths(root)
    expected_files = manifest["files"]
    if expected_files["telemetry"] != paths.telemetry.name:
        raise ValueError("dataset manifest has unexpected telemetry filename")
    if expected_files["alarm_events"] != paths.alarm_events.name:
        raise ValueError("dataset manifest has unexpected alarm_events filename")
    if expected_files["link_events"] != paths.link_events.name:
        raise ValueError("dataset manifest has unexpected link_events filename")
    for path in (paths.telemetry, paths.alarm_events, paths.link_events):
        if not path.is_file():
            raise ValueError(f"dataset evidence file is missing: {path.name}")

    expected_digests = manifest["sha256"]
    actual = DatasetDigests(
        telemetry_sha256=_sha256(paths.telemetry),
        alarm_events_sha256=_sha256(paths.alarm_events),
        link_events_sha256=_sha256(paths.link_events),
    )
    if actual != expected_digests:
        raise ValueError("dataset evidence digest mismatch")
    return paths


def normalize_peak_rss_bytes(raw_peak_rss: int, system: str) -> int | None:
    """Normalize ``ru_maxrss`` to bytes for supported Linux and macOS hosts."""

    if isinstance(raw_peak_rss, bool) or not isinstance(raw_peak_rss, int):
        raise TypeError("raw_peak_rss must be an integer")
    if raw_peak_rss < 0:
        raise ValueError("raw_peak_rss must be non-negative")
    if system == "Linux":
        return raw_peak_rss * 1024
    if system == "Darwin":
        return raw_peak_rss
    return None


def peak_rss_bytes() -> int | None:
    """Return normalized process peak RSS when the host unit is documented."""

    usage = resource.getrusage(resource.RUSAGE_SELF)
    return normalize_peak_rss_bytes(int(usage.ru_maxrss), platform.system())


def current_rss_bytes() -> int | None:
    """Return current RSS on Linux/macOS without adding a Python dependency."""

    system = platform.system()
    if system == "Linux":
        statm = Path("/proc/self/statm")
        try:
            fields = statm.read_text(encoding="ascii").split()
            resident_pages = int(fields[1])
            page_size = os.sysconf("SC_PAGE_SIZE")
        except (IndexError, OSError, ValueError):
            return None
        if not isinstance(page_size, int) or page_size <= 0:
            return None
        return resident_pages * page_size
    if system == "Darwin":
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(os.getpid())],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        try:
            return int(result.stdout.strip()) * 1024
        except ValueError:
            return None
    return None

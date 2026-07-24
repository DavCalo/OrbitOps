#!/usr/bin/env python3
"""Render a deterministic SVG portfolio visual from a real OrbitOps demo capture."""

from __future__ import annotations

import html
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_FORMAT_RE = re.compile(r"^format: (?P<format>\S+)$", re.MULTILINE)
_STATUS_RE = re.compile(r"^status: (?P<status>.+)$", re.MULTILINE)
_EVIDENCE_RE = re.compile(
    r"^evidence: operator-selected bundle; cross-stream provenance "
    r"(?P<provenance>verified|unverified)$",
    re.MULTILINE,
)
_TIMELINE_RE = re.compile(
    r"^timeline: rendered=(?P<rendered>\d+) matched=(?P<matched>\d+) "
    r"total=(?P<total>\d+) truncated=(?P<truncated>true|false)$",
    re.MULTILINE,
)
_DIAGNOSTICS_RE = re.compile(r"^diagnostics: (?P<count>\d+)$", re.MULTILINE)
_SUMMARY_RE = re.compile(
    r"^session inspection demo ok: "
    r"version=(?P<version>\S+) "
    r"profile=(?P<profile>\S+) "
    r"policy=(?P<policy>\S+) "
    r"received=(?P<received>\d+) "
    r"dropped=(?P<dropped>\d+) "
    r"delayed=(?P<delayed>\d+) "
    r"forwarded=(?P<forwarded>\d+) "
    r"alarms=(?P<alarms>\d+) "
    r"timeline=(?P<timeline>\d+)$",
    re.MULTILINE,
)
_TELEMETRY_RE = re.compile(
    r"^  counters: packets_decoded=(?P<decoded>\d+) "
    r"packets_rejected=(?P<rejected>\d+) "
    r"records_total=(?P<records>\d+) "
    r"sequence_duplicates=(?P<duplicates>\d+) "
    r"sequence_gaps=(?P<gaps>\d+)$",
    re.MULTILINE,
)
_ALARM_RE = re.compile(
    r"^  counters: transitions_cleared=(?P<cleared>\d+) "
    r"transitions_raised=(?P<raised>\d+) "
    r"transitions_total=(?P<total>\d+) "
    r"transitions_updated=(?P<updated>\d+)$",
    re.MULTILINE,
)
_LINK_RE = re.compile(
    r"^  counters: deliveries_forwarded=(?P<forwarded>\d+) "
    r"deliveries_scheduled=(?P<scheduled>\d+) "
    r"packets_corrupted=(?P<corrupted>\d+) "
    r"packets_delayed=(?P<delayed>\d+) "
    r"packets_dropped=(?P<dropped>\d+) "
    r"packets_duplicated=(?P<duplicated>\d+) "
    r"packets_received=(?P<received>\d+) "
    r"packets_reordered=(?P<reordered>\d+)$",
    re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class DemoSnapshot:
    report_format: str
    status: str
    provenance_verified: bool
    version: str
    profile: str
    policy: str
    received: int
    dropped: int
    delayed: int
    forwarded: int
    alarms: int
    timeline_total: int
    timeline_matched: int
    timeline_rendered: int
    timeline_truncated: bool
    diagnostics: int
    telemetry_decoded: int
    telemetry_gaps: int
    alarm_raised: int
    alarm_updated: int
    link_corrupted: int
    link_duplicated: int
    link_reordered: int


def _match(pattern: re.Pattern[str], text: str, description: str) -> re.Match[str]:
    match = pattern.search(text)
    if match is None:
        raise ValueError(f"capture is missing {description}")
    return match


def _integer(match: re.Match[str], name: str) -> int:
    return int(match.group(name))


def parse_capture(text: str) -> DemoSnapshot:
    report_format = _match(_FORMAT_RE, text, "report format")
    status = _match(_STATUS_RE, text, "report status")
    evidence = _match(_EVIDENCE_RE, text, "evidence provenance")
    timeline = _match(_TIMELINE_RE, text, "timeline summary")
    diagnostics = _match(_DIAGNOSTICS_RE, text, "diagnostic count")
    summary = _match(_SUMMARY_RE, text, "final deterministic summary")
    telemetry = _match(_TELEMETRY_RE, text, "telemetry counters")
    alarm = _match(_ALARM_RE, text, "alarm counters")
    link = _match(_LINK_RE, text, "link counters")

    snapshot = DemoSnapshot(
        report_format=report_format.group("format"),
        status=status.group("status"),
        provenance_verified=evidence.group("provenance") == "verified",
        version=summary.group("version"),
        profile=summary.group("profile"),
        policy=summary.group("policy"),
        received=_integer(summary, "received"),
        dropped=_integer(summary, "dropped"),
        delayed=_integer(summary, "delayed"),
        forwarded=_integer(summary, "forwarded"),
        alarms=_integer(summary, "alarms"),
        timeline_total=_integer(summary, "timeline"),
        timeline_matched=_integer(timeline, "matched"),
        timeline_rendered=_integer(timeline, "rendered"),
        timeline_truncated=timeline.group("truncated") == "true",
        diagnostics=_integer(diagnostics, "count"),
        telemetry_decoded=_integer(telemetry, "decoded"),
        telemetry_gaps=_integer(telemetry, "gaps"),
        alarm_raised=_integer(alarm, "raised"),
        alarm_updated=_integer(alarm, "updated"),
        link_corrupted=_integer(link, "corrupted"),
        link_duplicated=_integer(link, "duplicated"),
        link_reordered=_integer(link, "reordered"),
    )

    if snapshot.report_format != "orbitops.session_report/v1":
        raise ValueError(f"unsupported report format: {snapshot.report_format!r}")
    if snapshot.status != "complete compatible":
        raise ValueError(f"capture report is not complete and compatible: {snapshot.status!r}")
    if snapshot.provenance_verified:
        raise ValueError("capture unexpectedly claims verified cross-stream provenance")
    if snapshot.timeline_total != _integer(timeline, "total"):
        raise ValueError("final summary and report timeline totals disagree")
    if snapshot.timeline_matched != snapshot.timeline_total:
        raise ValueError("flagship preview must match the complete unfiltered timeline")
    if not snapshot.timeline_truncated or not (
        0 < snapshot.timeline_rendered < snapshot.timeline_matched
    ):
        raise ValueError("flagship preview must expose explicit bounded truncation")
    if snapshot.alarms != _integer(alarm, "total"):
        raise ValueError("final summary and alarm counters disagree")
    if snapshot.received != _integer(link, "received"):
        raise ValueError("final summary and link received counters disagree")
    if snapshot.dropped != _integer(link, "dropped"):
        raise ValueError("final summary and link drop counters disagree")
    if snapshot.delayed != _integer(link, "delayed"):
        raise ValueError("final summary and link delayed counters disagree")
    if snapshot.forwarded != _integer(link, "forwarded"):
        raise ValueError("final summary and link forwarded counters disagree")
    if snapshot.telemetry_decoded != snapshot.forwarded:
        raise ValueError("decoded telemetry and forwarded delivery counts disagree")
    if snapshot.dropped + snapshot.forwarded != snapshot.received:
        raise ValueError("link accounting does not reconcile received packets")
    return snapshot


def _text(
    x: int,
    y: int,
    value: str,
    css_class: str,
    *,
    max_chars: int | None = None,
    anchor: str | None = None,
) -> str:
    # The visual uses a monospace font. Explicit line budgets fail closed before text can
    # cross a card boundary when deterministic demo labels or counters change.
    if max_chars is not None and len(value) > max_chars:
        raise ValueError(f"visual text exceeds {max_chars}-character layout budget: {value!r}")
    escaped = html.escape(value)
    anchor_attribute = f' text-anchor="{anchor}"' if anchor is not None else ""
    return f'<text x="{x}" y="{y}" class="{css_class}"{anchor_attribute}>{escaped}</text>'


def render_svg(snapshot: DemoSnapshot) -> str:
    status_label = snapshot.status.upper().replace(" ", "\u00a0•\u00a0")
    delivered_percent = (
        round((snapshot.forwarded / snapshot.received) * 100) if snapshot.received else 0
    )
    delivered_width = (
        round(282 * snapshot.forwarded / snapshot.received) if snapshot.received else 0
    )
    link_detail = f"{snapshot.dropped} dropped · {snapshot.forwarded} forwarded"
    telemetry_detail = f"{snapshot.telemetry_gaps} sequence gaps"
    alarm_detail = f"{snapshot.alarm_raised} raised · {snapshot.alarm_updated} updated"
    evidence_note = (
        "Telemetry and alarms correlate by packet sequence; link evidence remains independent."
    )

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="620" '
        'viewBox="0 0 1200 620" role="img" aria-labelledby="title desc">',
        '<title id="title">OrbitOps deterministic session-inspection demo</title>',
        (
            '<desc id="desc">A real installed OrbitOps workflow using the '
            f"{html.escape(snapshot.profile)} link profile and "
            f"{html.escape(snapshot.policy)} alarm policy. "
            f"{snapshot.received} packets were received, "
            f"{snapshot.telemetry_decoded} were decoded after {snapshot.dropped} drops, "
            f"{snapshot.alarms} alarm transitions were recorded, and the final report was "
            "complete and compatible.</desc>"
        ),
        "<style>",
        "  .bg{fill:#07111f}.panel{fill:#0d1b2a;stroke:#26384d;stroke-width:1.5}",
        "  .terminal{fill:#08131f;stroke:#2c425a;stroke-width:2}",
        "  .title{fill:#f8fafc;font:700 30px ui-monospace,SFMono-Regular,Menlo,monospace}",
        "  .subtitle{fill:#93a4b8;font:15px ui-monospace,SFMono-Regular,Menlo,monospace}",
        (
            "  .label{fill:#93a4b8;font:600 13px "
            "ui-monospace,SFMono-Regular,Menlo,monospace;"
            "letter-spacing:1.5px}"
        ),
        "  .value{fill:#f8fafc;font:700 44px ui-monospace,SFMono-Regular,Menlo,monospace}",
        "  .metric{fill:#dbe7f3;font:600 16px ui-monospace,SFMono-Regular,Menlo,monospace}",
        "  .detail{fill:#dbe7f3;font:14px ui-monospace,SFMono-Regular,Menlo,monospace}",
        "  .context{fill:#93a4b8;font:12px ui-monospace,SFMono-Regular,Menlo,monospace}",
        "  .evidence{fill:#f8fafc;font:700 21px ui-monospace,SFMono-Regular,Menlo,monospace}",
        "  .small{fill:#93a4b8;font:12px ui-monospace,SFMono-Regular,Menlo,monospace}",
        "  .ok{fill:#4ade80}.accent{fill:#38bdf8}.warn{fill:#fbbf24}",
        "  .track{fill:#1d3045}.bar{fill:#38bdf8}",
        "  .divider{stroke:#26384d;stroke-width:1.5}",
        (
            "  .arrow{stroke:#38bdf8;stroke-width:2;fill:none;"
            "stroke-linecap:round;stroke-linejoin:round}"
        ),
        "</style>",
        '<rect class="bg" width="1200" height="620" rx="24"/>',
        '<rect class="terminal" x="32" y="32" width="1136" height="556" rx="24"/>',
        _text(72, 82, "OrbitOps session inspection", "title", max_chars=32),
        _text(
            72,
            112,
            "deterministic installed workflow · real evidence · bounded operator preview",
            "subtitle",
            max_chars=76,
        ),
        '<rect x="874" y="54" width="242" height="46" rx="23" fill="#123523" stroke="#2e8b57"/>',
        _text(995, 83, status_label, "detail ok", max_chars=24, anchor="middle"),
        '<rect class="panel" x="66" y="151" width="330" height="190" rx="16"/>',
        _text(90, 182, "LINK EMULATOR", "label", max_chars=20),
        _text(90, 235, str(snapshot.received), "value", max_chars=4),
        _text(90, 267, "packets received", "metric", max_chars=24),
        _text(90, 294, link_detail, "detail", max_chars=30),
        _text(90, 317, snapshot.profile, "context", max_chars=24),
        _text(
            372,
            317,
            f"{delivered_percent}%",
            "context accent",
            max_chars=4,
            anchor="end",
        ),
        '<rect class="track" x="90" y="324" width="282" height="8" rx="4"/>',
        f'<rect class="bar" x="90" y="324" width="{delivered_width}" height="8" rx="4"/>',
        '<path class="arrow" d="M 402 255 H 417 M 411 249 L 417 255 L 411 261"/>',
        '<rect class="panel" x="426" y="151" width="330" height="190" rx="16"/>',
        _text(450, 182, "GROUND STATION", "label", max_chars=20),
        _text(450, 235, str(snapshot.telemetry_decoded), "value", max_chars=4),
        _text(450, 267, "validated telemetry", "metric", max_chars=24),
        _text(450, 304, telemetry_detail, "detail warn", max_chars=28),
        _text(450, 329, "strict validation · JSONL v1", "context", max_chars=38),
        '<path class="arrow" d="M 762 255 H 777 M 771 249 L 777 255 L 771 261"/>',
        '<rect class="panel" x="786" y="151" width="330" height="190" rx="16"/>',
        _text(810, 182, "ALARM LIFECYCLE", "label", max_chars=20),
        _text(810, 235, str(snapshot.alarms), "value", max_chars=4),
        _text(810, 267, "auditable transitions", "metric", max_chars=24),
        _text(810, 304, alarm_detail, "detail", max_chars=28),
        _text(810, 329, f"{snapshot.policy} · SAFE-mode entry", "context", max_chars=38),
        '<rect class="panel" x="66" y="375" width="1050" height="152" rx="16"/>',
        _text(90, 405, "REPORT EVIDENCE", "label", max_chars=20),
        _text(90, 455, f"{snapshot.timeline_total} timeline entries", "evidence", max_chars=26),
        '<line class="divider" x1="374" y1="426" x2="374" y2="474"/>',
        _text(410, 455, f"{snapshot.diagnostics} diagnostics", "evidence", max_chars=22),
        '<line class="divider" x1="624" y1="426" x2="624" y2="474"/>',
        _text(660, 455, f"{snapshot.timeline_rendered}-entry preview", "evidence", max_chars=24),
        _text(90, 497, evidence_note, "small", max_chars=92),
        _text(72, 562, f"OrbitOps {snapshot.version}", "small", max_chars=24),
        _text(600, 562, snapshot.report_format, "small", max_chars=36, anchor="middle"),
        _text(
            1128,
            562,
            "generated from validated demo output",
            "small",
            max_chars=42,
            anchor="end",
        ),
        "</svg>",
        "",
    ]
    return "\n".join(lines)


def _write_atomically(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> int:
    if len(sys.argv) != 3:
        print(
            f"usage: {Path(sys.argv[0]).name} CAPTURE.txt OUTPUT.svg",
            file=sys.stderr,
        )
        return 2

    capture_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    try:
        snapshot = parse_capture(capture_path.read_text(encoding="utf-8"))
        _write_atomically(output_path, render_svg(snapshot))
    except (OSError, ValueError) as exc:
        print(f"session demo visual failed: {exc}", file=sys.stderr)
        return 1

    print(f"session demo visual written: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

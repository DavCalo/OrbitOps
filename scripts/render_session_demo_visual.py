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

_STATUS_RE = re.compile(r"^status: (?P<status>.+)$", re.MULTILINE)
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
    status: str
    version: str
    profile: str
    policy: str
    received: int
    dropped: int
    delayed: int
    forwarded: int
    alarms: int
    timeline_total: int
    timeline_rendered: int
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
    status = _match(_STATUS_RE, text, "report status")
    timeline = _match(_TIMELINE_RE, text, "timeline summary")
    diagnostics = _match(_DIAGNOSTICS_RE, text, "diagnostic count")
    summary = _match(_SUMMARY_RE, text, "final deterministic summary")
    telemetry = _match(_TELEMETRY_RE, text, "telemetry counters")
    alarm = _match(_ALARM_RE, text, "alarm counters")
    link = _match(_LINK_RE, text, "link counters")

    snapshot = DemoSnapshot(
        status=status.group("status"),
        version=summary.group("version"),
        profile=summary.group("profile"),
        policy=summary.group("policy"),
        received=_integer(summary, "received"),
        dropped=_integer(summary, "dropped"),
        delayed=_integer(summary, "delayed"),
        forwarded=_integer(summary, "forwarded"),
        alarms=_integer(summary, "alarms"),
        timeline_total=_integer(summary, "timeline"),
        timeline_rendered=_integer(timeline, "rendered"),
        diagnostics=_integer(diagnostics, "count"),
        telemetry_decoded=_integer(telemetry, "decoded"),
        telemetry_gaps=_integer(telemetry, "gaps"),
        alarm_raised=_integer(alarm, "raised"),
        alarm_updated=_integer(alarm, "updated"),
        link_corrupted=_integer(link, "corrupted"),
        link_duplicated=_integer(link, "duplicated"),
        link_reordered=_integer(link, "reordered"),
    )

    if snapshot.timeline_total != _integer(timeline, "total"):
        raise ValueError("final summary and report timeline totals disagree")
    if snapshot.alarms != _integer(alarm, "total"):
        raise ValueError("final summary and alarm counters disagree")
    if snapshot.received != _integer(link, "received"):
        raise ValueError("final summary and link received counters disagree")
    if snapshot.dropped != _integer(link, "dropped"):
        raise ValueError("final summary and link drop counters disagree")
    if snapshot.forwarded != _integer(link, "forwarded"):
        raise ValueError("final summary and link forwarded counters disagree")
    if snapshot.telemetry_decoded != snapshot.forwarded:
        raise ValueError("decoded telemetry and forwarded delivery counts disagree")
    return snapshot


def _text(x: int, y: int, value: str, css_class: str) -> str:
    escaped = html.escape(value)
    return f'<text x="{x}" y="{y}" class="{css_class}">{escaped}</text>'


def render_svg(snapshot: DemoSnapshot) -> str:
    status_label = snapshot.status.upper().replace(" ", "  •  ")
    link_quality = snapshot.forwarded / snapshot.received if snapshot.received else 0.0
    delivered_percent = round(link_quality * 100)
    clean_link = (
        snapshot.link_corrupted == 0
        and snapshot.link_duplicated == 0
        and snapshot.link_reordered == 0
    )
    clean_label = (
        "no corruption / duplicates / reordering" if clean_link else "additional faults observed"
    )
    alarm_counts = f"{snapshot.alarm_raised} raised  ·  {snapshot.alarm_updated} updated"
    report_line = f"orbitops.session_report/v1  ·  timeline {snapshot.timeline_total} entries"
    preview_line = (
        f"{snapshot.diagnostics} diagnostics  ·  "
        f"preview rendered {snapshot.timeline_rendered} entries"
    )
    correlation_line = (
        "telemetry + alarm correlation by unique packet sequence; link remains a separate lane"
    )
    footer = (
        f"OrbitOps {snapshot.version}  ·  profile={snapshot.profile}  ·  policy={snapshot.policy}"
    )

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" '
        'viewBox="0 0 1200 720" role="img" aria-labelledby="title desc">',
        '<title id="title">OrbitOps deterministic session-inspection demo</title>',
        '<desc id="desc">A real OrbitOps run using the intermittent-loss link profile and '
        "thermal-demo alarm policy. Fifty-two packets were received by the link emulator, "
        "seven were dropped, forty-five were forwarded and decoded, nine alarm transitions "
        "were recorded, and the final report was complete and compatible.</desc>",
        "<style>",
        "  .bg{fill:#07111f}.panel{fill:#0d1b2a;stroke:#26384d;stroke-width:1.5}",
        "  .terminal{fill:#08131f;stroke:#2c425a;stroke-width:2}",
        "  .title{fill:#f8fafc;font:700 30px ui-monospace,SFMono-Regular,Menlo,monospace}",
        "  .subtitle{fill:#93a4b8;font:16px ui-monospace,SFMono-Regular,Menlo,monospace}",
        "  .label{fill:#93a4b8;font:14px ui-monospace,SFMono-Regular,Menlo,monospace}",
        "  .value{fill:#f8fafc;font:700 34px ui-monospace,SFMono-Regular,Menlo,monospace}",
        "  .body{fill:#dbe7f3;font:16px ui-monospace,SFMono-Regular,Menlo,monospace}",
        "  .small{fill:#93a4b8;font:13px ui-monospace,SFMono-Regular,Menlo,monospace}",
        "  .ok{fill:#4ade80}.warn{fill:#fbbf24}.accent{fill:#38bdf8}",
        "  .track{fill:#1d3045}.bar{fill:#38bdf8}.line{stroke:#35506c;stroke-width:2}",
        "</style>",
        '<rect class="bg" width="1200" height="720" rx="24"/>',
        '<rect class="terminal" x="38" y="38" width="1124" height="644" rx="18"/>',
        '<circle cx="70" cy="70" r="7" fill="#fb7185"/>',
        '<circle cx="94" cy="70" r="7" fill="#fbbf24"/>',
        '<circle cx="118" cy="70" r="7" fill="#4ade80"/>',
        _text(66, 125, "OrbitOps / session inspect", "title"),
        _text(
            66,
            153,
            "real deterministic run · dynamic ports and timestamps omitted",
            "subtitle",
        ),
        '<rect x="825" y="104" width="292" height="48" rx="24" fill="#123523" stroke="#2e8b57"/>',
        _text(851, 136, status_label, "body ok"),
        '<rect class="panel" x="66" y="190" width="330" height="162" rx="14"/>',
        _text(88, 220, "LINK EMULATOR", "label"),
        _text(88, 265, str(snapshot.received), "value"),
        _text(170, 265, "received", "body"),
        _text(88, 300, f"{snapshot.dropped} dropped  ·  {snapshot.forwarded} forwarded", "body"),
        _text(88, 326, f"{snapshot.delayed} delayed  ·  {clean_label}", "small"),
        '<rect class="track" x="88" y="338" width="280" height="8" rx="4"/>',
        f'<rect class="bar" x="88" y="338" width="{round(280 * link_quality)}" height="8" rx="4"/>',
        _text(306, 331, f"{delivered_percent}%", "small accent"),
        '<rect class="panel" x="435" y="190" width="330" height="162" rx="14"/>',
        _text(457, 220, "GROUND STATION", "label"),
        _text(457, 265, str(snapshot.telemetry_decoded), "value"),
        _text(539, 265, "decoded", "body"),
        _text(457, 300, f"{snapshot.telemetry_gaps} sequence gaps detected", "body"),
        _text(457, 326, "strict packet validation · telemetry JSONL v1", "small"),
        '<rect class="panel" x="804" y="190" width="313" height="162" rx="14"/>',
        _text(826, 220, "ALARM LIFECYCLE", "label"),
        _text(826, 265, str(snapshot.alarms), "value"),
        _text(885, 265, "transitions", "body"),
        _text(826, 300, alarm_counts, "body"),
        _text(826, 326, "thermal escalation · SAFE-mode entry", "small"),
        '<line class="line" x1="232" y1="382" x2="966" y2="382"/>',
        '<circle cx="232" cy="382" r="8" class="accent"/>',
        '<circle cx="599" cy="382" r="8" class="accent"/>',
        '<circle cx="966" cy="382" r="8" class="accent"/>',
        _text(175, 414, "C++ simulator", "body"),
        _text(520, 414, snapshot.profile, "body"),
        _text(900, 414, snapshot.policy, "body"),
        _text(139, 438, "52 thermal packets", "small"),
        _text(500, 438, "seeded loss + latency", "small"),
        _text(891, 438, "auditable transitions", "small"),
        '<rect class="panel" x="66" y="472" width="1051" height="142" rx="14"/>',
        _text(88, 505, "REPORT EVIDENCE", "label"),
        _text(88, 544, report_line, "body"),
        _text(88, 573, preview_line, "body"),
        _text(88, 600, correlation_line, "small"),
        _text(66, 652, footer, "small"),
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

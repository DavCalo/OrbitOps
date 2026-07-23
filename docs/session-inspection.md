# Session inspection

`orbitops session inspect` builds one deterministic operator report from any supported combination
of OrbitOps telemetry recordings, alarm-event logs, and link-event logs.

## Public workflow

```bash
orbitops session inspect \
  --telemetry sessions/mission-telemetry.jsonl \
  --link-events sessions/mission-link-events.jsonl \
  --alarm-events sessions/mission-alarms.jsonl
```

At least one evidence source is required. Missing lanes remain explicit incomplete sources rather
than being silently removed from the report.

## Flagship installed demo

Run the complete C++ and Python operator workflow with:

```bash
make session-demo
```

The demo uses the installed `orbitops` executable, the C++ thermal simulator, the
`intermittent-loss` mission profile, and the `thermal-demo` alarm policy. It creates isolated
telemetry, link-event, and alarm-event evidence, validates their summaries and identities, and
invokes the installed session inspector in text and JSON modes.

The deterministic reference run receives 52 packets at the link emulator, drops seven, forwards
and decodes 45, reports six telemetry sequence gaps, and records nine alarm transitions. The
operator should notice that telemetry and alarm evidence correlate by unique packet sequence while
link evidence remains a separate lane.

The README visual is generated from a real captured run rather than a fabricated mock-up. Regenerate
it after intentional demo-output changes with:

```bash
python_cmd="$PWD/.venv/bin/python"
capture="$(mktemp)"

PATH="$PWD/.venv/bin:$PATH" \
  make PYTHON="$python_cmd" session-demo > "$capture"

PATH="$PWD/.venv/bin:$PATH" \
  "$python_cmd" scripts/render_session_demo_visual.py \
  "$capture" docs/assets/session-demo.svg

rm -f "$capture"
```

The renderer validates agreement between report counters and the final demo summary. It omits
dynamic ports, temporary paths, run identifiers, and timestamps from the committed SVG.

## Evidence boundaries

Each source is loaded through its existing strict contract:

- telemetry recording JSONL version `1`;
- alarm-event JSONL version `1`;
- link-event JSONL versions `1` and `2`.

The inspector does not invent a common run identifier, clock, or provenance guarantee. Telemetry
and alarm entries correlate exactly only when the selected telemetry contains one unique decoded
record with the alarm packet sequence. Duplicate candidates remain incompatible and visible.
Missing candidates remain visible but do not fabricate a match. Link `packet_index` is not
telemetry `packet_sequence`, so link evidence remains a separate lane.

## Report formats

The default text report contains stable sections for report metadata, whole-session summary,
source summaries, diagnostics, and timeline entries.

Use JSON for automation:

```bash
orbitops session inspect \
  --telemetry sessions/mission-telemetry.jsonl \
  --format json
```

The JSON format identifier is:

```text
orbitops.session_report/v1
```

Version `1` preserves deterministic key ordering and the top-level metadata, summary, sources,
diagnostics, and timeline sections. The selection section distinguishes rendered, matching, and
unfiltered timeline counts so automation never has to parse a diagnostic message to understand
truncation. Consumers must reject unknown report-format versions instead of guessing
compatibility.

## Filters

Filters are combined with logical AND:

```bash
orbitops session inspect \
  --telemetry sessions/mission-telemetry.jsonl \
  --alarm-events sessions/mission-alarms.jsonl \
  --sequence-min 100 \
  --sequence-max 200 \
  --alarm-code HIGH_TEMPERATURE \
  --alarm-severity critical \
  --limit 50
```

Supported filters are:

- inclusive packet-sequence minimum and maximum;
- exact normalized alarm code;
- alarm severity `warning` or `critical`;
- explicit timeline limit, bounded to 10,000 entries.

Filters change rendered timeline entries only. Source summaries, diagnostics, completeness,
compatibility, and whole-session counters continue to describe the unfiltered evidence. When an
event limit omits matching entries, the report includes an explicit truncation diagnostic and
retains the unfiltered totals.

## Output files

Without `--output`, the report is written to standard output.

```bash
orbitops session inspect \
  --telemetry sessions/mission-telemetry.jsonl \
  --format json \
  --output sessions/mission-report.json
```

Output files are replaced atomically through a temporary file in the destination directory.
Failures or interruptions before replacement remove the temporary file and preserve an existing
destination; once replacement succeeds, the destination contains one complete report. `--output`
is rejected as a usage error when it refers to any selected evidence file, including filesystem
aliases, so inspection cannot overwrite its own inputs.

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Supported session with no explicitly incomplete source |
| `1` | Structurally valid but incomplete selected evidence |
| `2` | Command-line usage error reserved for `argparse` |
| `3` | Incompatible or ambiguous evidence |
| `4` | Malformed evidence |
| `5` | Filesystem or other input/output failure |

Incompatibility takes precedence over incompleteness. Malformed and incompatible inputs never
produce exit code `0`.

## Security and privacy

Selected paths and source-local identifiers may be sensitive operator metadata. Error messages
identify the affected source without printing raw telemetry bytes. JSON contains no ANSI escape
sequences. Report fingerprints and source identifiers are reproducibility context, not
authentication or provenance proof.

## Validation

The repository validates:

- stable text and JSON serialization;
- report immutability and schema-version metadata;
- direct coverage of exit codes `0` through `5`;
- filter combinations and explicit truncation;
- output replacement and failure cleanup;
- the installed command from the built wheel;
- Linux and macOS installed workflows in CI.

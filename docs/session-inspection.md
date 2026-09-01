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

## Performance and soak evidence

Issue #42 establishes a reproducible performance baseline for the existing inspector. It does not
define a cross-platform speed threshold and it does not treat one soak as a reliability guarantee.
The retained reference evidence was produced from commit
`6cd9aec9a5e114b3f5bfa88048adeaf9c2df481f` on Darwin/arm64 with CPython 3.13.7 and eight logical
CPUs.

The benchmark uses one warm-up and five measured samples per scale. Every warm-up and measured
sample runs in a fresh Python subprocess; aggregates use the median of successful measured samples
while retaining mean, minimum, maximum, and every failed sample in the raw result. Peak RSS is
normalized to bytes across Linux and macOS before aggregation. Successful raw samples also retain
a non-negative reconciliation gap between the sum of measured phases and the enclosing total; the
validator rejects phase timings that fall outside that measured total.

| Scale | Telemetry | Input records | Load/parse median | Normalize/correlate median | Render/serialize median | Total median | Peak RSS median | Report bytes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| small | 250 | 1,014 | 0.005220 s | 0.005292 s | 0.003399 s | 0.013930 s | 31,342,592 | 400,893 |
| medium | 2,500 | 10,104 | 0.049382 s | 0.099503 s | 0.033427 s | 0.182025 s | 49,643,520 | 4,016,337 |
| large | 10,000 | 40,404 | 0.195897 s | 1.061731 s | 0.152839 s | 1.415386 s | 103,907,328 | 16,117,083 |

The reference samples contain no benchmark failures. Load/parse and report size remain close to
input-linear across these scales, while normalize/correlate becomes the dominant phase at the
large scale (median 1.061731 s of 1.415386 s total). This is a measured baseline characteristic,
not an optimization requirement or performance promise.

The retained 60-minute soak uses the medium dataset in one long-lived Python process with one
iteration scheduled per second and resource sampling every 60 seconds. It completed 3,601 of 3,601
iterations successfully in 3,600.257 seconds. The final report remained complete and compatible,
with 10,104 input records, 10,100 timeline entries, three sources, zero diagnostics, and a
4,016,337-byte JSON report. Median iteration wall time was approximately 0.2444 seconds; the 95th
percentile was approximately 0.2573 seconds.

Current RSS showed an early allocator/runtime transient: the post-first-cycle sample was
47,595,520 bytes, current RSS reached 143,245,312 bytes at approximately two minutes, and the
process-wide peak RSS reached 175,046,656 bytes. Current RSS then fell and stabilized; the final
sample was 45,498,368 bytes (2,097,152 bytes below the post-first-cycle baseline), and the last
30 minutes stayed within approximately 43.33--43.39 MiB. The observed run therefore does not show
monotonic resource growth after the initial transient. That observation is limited to this fixed
dataset, environment, duration, and commit and must not be generalized into a reliability claim.

Retained raw evidence:

- [`docs/evidence/session-inspection-benchmark-6cd9aec.json`](evidence/session-inspection-benchmark-6cd9aec.json)
  (`sha256:6ef5972a80dabc1d63a8be5198ff6a34137b882b7b5c67b5fffc4030dd48a559`);
- [`docs/evidence/session-inspection-soak-6cd9aec-60m.json`](evidence/session-inspection-soak-6cd9aec-60m.json)
  (`sha256:fb42cc4b43d3d10fb6123a010e1fbca81f015966dc67f5207f2de884036962d3`).

Reproduce deterministic datasets and the benchmark from a clean checkout of the measured commit:

```bash
python_cmd="$PWD/.venv/bin/python"
mkdir -p .local/issue42

for scale in small medium large; do
  "$python_cmd" scripts/session_inspection_benchmark.py generate \
    --scale "$scale" \
    --output-dir ".local/issue42/dataset-$scale"
done

"$python_cmd" scripts/session_inspection_benchmark.py benchmark \
  --scales small medium large \
  --samples 5 \
  --warmups 1 \
  --output .local/issue42/session-inspection-benchmark.json

"$python_cmd" scripts/session_inspection_benchmark.py validate \
  .local/issue42/session-inspection-benchmark.json
```

Run the qualifying local soak separately; it is intentionally not part of normal PR CI:

```bash
"$python_cmd" scripts/session_inspection_soak.py run \
  --scale medium \
  --duration-seconds 3600 \
  --iteration-interval-seconds 1 \
  --resource-sample-interval-seconds 60 \
  --output .local/issue42/session-inspection-soak-60m.json

"$python_cmd" scripts/session_inspection_soak.py validate \
  .local/issue42/session-inspection-soak-60m.json
```

On macOS, `caffeinate -i` may wrap the soak command to prevent idle sleep. It is not part of the
measured OrbitOps process. Keep the checkout clean while producing reference evidence so the
recorded commit SHA identifies the code actually exercised.

## Validation

The repository validates:

- stable text and JSON serialization;
- report immutability and schema-version metadata;
- direct coverage of exit codes `0` through `5`;
- filter combinations and explicit truncation;
- output replacement and failure cleanup;
- the installed command from the built wheel;
- Linux and macOS installed workflows in CI.

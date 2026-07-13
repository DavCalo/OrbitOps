# Operations guide

## Supported environment

- Python 3.11–3.13;
- C++17 compiler;
- CMake 3.20 or newer;
- Linux or macOS. Windows users should use WSL for the simulator.

OrbitOps is non-flight development software. Run it on loopback or a trusted isolated network.

## Install and build

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

cmake -S onboard -B build       -DCMAKE_BUILD_TYPE=Release       -DORBITOPS_WARNINGS_AS_ERRORS=ON
cmake --build build
```

## One-command alarm lifecycle demo

```bash
make alarm-demo
```

This v0.4.0 target:

1. builds or locates the C++ simulator;
2. invokes the installed `orbitops` executable;
3. selects the bundled `thermal-demo` alarm policy;
4. sends 52 deterministic thermal telemetry packets;
5. observes warning, critical-update, and SAFE-mode transitions;
6. stops the listener cooperatively with `SIGINT`;
7. validates policy identity and effective fingerprint;
8. validates exact lifecycle ordering and final counters.

Expected transition order:

```text
sequence 7  -> alarm_raised  ELEVATED_TEMPERATURE
sequence 18 -> alarm_updated HIGH_TEMPERATURE
sequence 51 -> alarm_raised  SAFE_MODE
```

The earlier profile and explicit-link workflows remain available through `make profile-demo`
and `make link-demo`.

## Alarm-policy commands

```bash
orbitops alarm-policy list
orbitops alarm-policy show thermal-demo
orbitops alarm-policy validate file:policies/lab-policy.toml
```

Reference forms:

- `thermal-demo`: short built-in name unless an identically named local file exists;
- `builtin:thermal-demo`: explicit built-in;
- `policy.toml`: existing external file;
- `file:policy.toml`: explicit external file.

Ambiguous short references are rejected before the receiver binds UDP or creates recordings.

## Record a manual thermal alarm pass

```bash
orbitops listen       --host 127.0.0.1       --port 9000       --alarm-policy thermal-demo       --record sessions/thermal-telemetry.jsonl       --alarm-log sessions/thermal-alarms.jsonl
```

In another terminal:

```bash
./build/orbitops_sim       --host 127.0.0.1       --port 9000       --interval-ms 100       --packets 52       --scenario thermal
```

Stop the listener with `Ctrl+C` after the simulator completes. Cooperative shutdown writes the
final alarm summary. Telemetry and alarm events remain separate files.

## Inspect an alarm log

```bash
python - <<'PY'
from pathlib import Path
from orbitops.alarm_events import (
    load_alarm_events,
    run_metadata_from_events,
    validate_run_summary,
)

events = load_alarm_events(Path("sessions/thermal-alarms.jsonl"))
print(run_metadata_from_events(events))
print(validate_run_summary(events))
PY
```

A complete stream begins with policy-aware `run_metadata` and ends with `run_summary`.
Transition records contain packet sequence, stable identity, code, severity, observed value,
and threshold.

## One-command mission-profile demo

```bash
make profile-demo
```

This target uses the installed CLI, the `intermittent-loss` profile, 16 C++ packets, and
schema-version-2 link events. It validates deterministic drops, profile identity, effective
fingerprint, forwarded packets, and final counters.

## Run a profile-driven linked session

Terminal 1:

```bash
orbitops listen       --host 127.0.0.1       --port 9000       --alarm-policy conservative       --record sessions/telemetry.jsonl       --alarm-log sessions/alarm-events.jsonl
```

Terminal 2:

```bash
orbitops link       --profile degraded-link       --listen-host 127.0.0.1       --listen-port 9001       --forward-host 127.0.0.1       --forward-port 9000       --event-log sessions/link-events.jsonl       --session-id local-profile-pass
```

Terminal 3:

```bash
./build/orbitops_sim       --host 127.0.0.1       --port 9001       --interval-ms 500       --packets 80       --scenario thermal
```

The simulator targets the link listener, not the ground-station port.

## Configuration precedence

Link configuration:

```text
OrbitOps defaults -> selected profile -> explicit CLI options
```

Alarm behavior is selected by one resolved policy. Omitting `--alarm-policy` uses
`builtin:standard`, which preserves the v0.3 effective thresholds and zero hysteresis.

Invalid profiles, policies, and CLI values fail before their associated socket or log side
effects.

## Log handling

- `--record PATH` stores raw packet bytes as telemetry-recording JSONL;
- `link --event-log PATH` stores impairment and forwarding metadata;
- `listen --alarm-log PATH` stores decoded alarm decisions;
- each path is created or replaced for one run;
- do not concatenate or interchange these schemas.

Do not place secrets in session identifiers, profile names, policy names, or local references.
External references may reveal directory names. Alarm logs may reveal sequence numbers,
observed operational values, thresholds, modes, and human-readable messages.

Fingerprints are not authentication or provenance mechanisms. Anyone able to modify a policy
or log can replace both data and fingerprint.

## Finite and interrupted runs

Link runs can use `--max-packets N` to drain scheduled deliveries and write their summary.

The listener is stopped cooperatively with `SIGINT`. Its context managers close telemetry
recording and write the final alarm summary. Forced termination, process crashes, or storage
failure may leave a partial alarm log without a summary; partial logs remain inspectable but do
not pass complete-run summary validation.

## Exit behavior

- `0`: successful command or cooperative operator stop;
- `1`: validated operational failure;
- `2`: command-line parsing failure.

## Troubleshooting

### Installed CLI not found

Activate the intended virtual environment and run:

```bash
python -m pip install -e .
command -v orbitops
```

### Policy not found or ambiguous

List built-ins with `orbitops alarm-policy list`. Use `builtin:<name>` or `file:<path>` to
select a namespace explicitly.

### Alarm log has no summary

Confirm the listener was stopped with `Ctrl+C` rather than forcibly killed. The partial log is
still readable, but `validate_run_summary` correctly rejects it.

### Unexpected transition sequence

Confirm the selected policy, policy fingerprint, simulator scenario, packet count, and absence
of packet loss. A sequence gap is itself an alarm occurrence.

### Address already in use

Choose another listen or forward port, or stop the conflicting process.

### CRC mismatch

A packet was modified or corrupted. CRC-32 detects accidental changes; it does not authenticate
or repair the datagram.

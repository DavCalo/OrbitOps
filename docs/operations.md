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

cmake -S onboard -B build   -DCMAKE_BUILD_TYPE=Release   -DORBITOPS_WARNINGS_AS_ERRORS=ON
cmake --build build
```

## One-command mission-profile demo

```bash
make profile-demo
```

This target:

1. invokes the installed `orbitops` executable;
2. selects the bundled `intermittent-loss` profile;
3. sends 16 C++ telemetry packets;
4. decodes every forwarded packet;
5. validates the deterministic drop count;
6. validates schema-version-2 run metadata;
7. verifies the effective configuration fingerprint and final summary.

The explicit-option v0.2 workflow remains available through `make link-demo`.

## Profile commands

```bash
orbitops profile list
orbitops profile show degraded-link
orbitops profile validate file:profiles/lab-pass.toml
```

Built-in names are stable. `show` and `validate` emit compact sorted-key JSON for scripting.

Reference forms:

- `nominal`: short built-in name, unless an identically named local file exists;
- `builtin:nominal`: explicit built-in;
- `scenario.toml`: existing external file;
- `file:scenario.toml`: explicit external file.

Ambiguous short references are rejected.

## Run a profile-driven session

Terminal 1:

```bash
orbitops listen   --host 127.0.0.1   --port 9000   --record sessions/telemetry.jsonl
```

Terminal 2:

```bash
orbitops link   --profile degraded-link   --listen-host 127.0.0.1   --listen-port 9001   --forward-host 127.0.0.1   --forward-port 9000   --event-log sessions/link-events.jsonl   --session-id local-profile-pass
```

Terminal 3:

```bash
./build/orbitops_sim   --host 127.0.0.1   --port 9001   --interval-ms 500   --packets 80   --scenario thermal
```

The simulator targets the link listener, not the ground-station port.

## Configuration precedence

```text
OrbitOps defaults -> selected profile -> explicit CLI options
```

For example, this keeps the profile seed and timing values but disables loss:

```bash
orbitops link --profile degraded-link --loss-rate 0
```

Invalid profiles and invalid CLI values fail before event-log creation, runtime construction, or socket binding.

## Event logs

`--event-log PATH` creates or replaces canonical JSONL. New logs use schema version `2` and begin with `run_metadata`.

Inspect a complete log:

```bash
python - <<'PY'
from pathlib import Path
from orbitops.link import (
    load_link_events,
    run_metadata_from_events,
    validate_run_summary,
)

events = load_link_events(Path("sessions/link-events.jsonl"))
print(run_metadata_from_events(events))
print(validate_run_summary(events))
PY
```

The run metadata identifies:

- the effective configuration fingerprint;
- selected profile name;
- original profile reference;
- profile schema version.

No-profile runs still contain a fingerprint, with profile fields set to `null`. Legacy schema-version-1 logs remain readable and return no run metadata.

A configuration fingerprint is not an authentication or provenance mechanism. Anyone able to modify the file can replace both data and fingerprint.

## Metadata handling

- Do not place secrets in session identifiers, profile names, or profile paths.
- External profile references may expose local directory names in logs.
- Store telemetry and link-event logs separately.
- Apply operating-system permissions and retention appropriate to the metadata.
- Copy important captures before reusing a path.

## Finite and interrupted runs

`--max-packets N` releases held tail packets, drains scheduled deliveries, writes `run_summary`, and exits.

`SIGINT` and `SIGTERM` request cooperative shutdown. Forced termination or storage failure may leave a structurally valid partial log without a summary.

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

### Profile not found or ambiguous

List built-ins with `orbitops profile list`. Use `builtin:<name>` or `file:<path>` to select a namespace explicitly.

### Fingerprint differs from an earlier run

Compare the effective values, not TOML formatting. Explicit CLI overrides change the fingerprint. Profile descriptions and names do not.

### Event log has no summary

The process was interrupted before normal completion, forcibly killed, or failed to write storage. The partial log remains inspectable, but summary validation correctly rejects it.

### Address already in use

Choose another listen or forward port, or stop the conflicting process.

### CRC mismatch

A packet was modified or corrupted. CRC-32 detects accidental changes; it does not authenticate or repair the datagram.

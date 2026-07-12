# Operations guide

## Supported environment

- Python 3.11–3.13;
- C++17 compiler;
- CMake 3.20 or newer;
- Linux or macOS. Windows users should use WSL for the simulator.

## Install the CLI

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
orbitops --version
```

## Build the simulator

```bash
cmake -S onboard -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DORBITOPS_WARNINGS_AS_ERRORS=ON
cmake --build build
./build/orbitops_sim --version
```

## Automated link demo

```bash
make link-demo
```

The target launches the public `orbitops link` command, sends four C++ telemetry packets through deterministic latency, duplication, and bounded reordering, decodes all forwarded packets, and validates the JSONL run summary.

## Run an impaired session

Use three terminals.

### Terminal 1: ground station

```bash
orbitops listen \
  --host 127.0.0.1 \
  --port 9000 \
  --record sessions/telemetry.jsonl
```

### Terminal 2: link emulator

```bash
orbitops link \
  --listen-host 127.0.0.1 \
  --listen-port 9001 \
  --forward-host 127.0.0.1 \
  --forward-port 9000 \
  --seed 42 \
  --loss-rate 0.05 \
  --latency-ms 120 \
  --jitter-ms 30 \
  --duplicate-rate 0.02 \
  --corrupt-rate 0.01 \
  --reorder-window 3 \
  --event-log sessions/link-events.jsonl \
  --session-id local-demo
```

### Terminal 3: simulator

```bash
./build/orbitops_sim \
  --host 127.0.0.1 \
  --port 9001 \
  --interval-ms 500 \
  --packets 80 \
  --scenario thermal
```

The simulator must target the link emulator's listen port, not the ground-station port.

## Link command semantics

```text
orbitops link [endpoint options] [impairment options] [observability options]
```

Endpoint defaults:

- listen: `127.0.0.1:9001`;
- forward: `127.0.0.1:9000`.

Impairment defaults are pass-through: seed `0`, all rates and delays `0`, and reorder window `0`.

Rates must be finite numbers from `0.0` to `1.0`. Timing and reorder values must be non-negative integers. Ports, seeds, and reorder windows are range-checked before sockets are opened.

`--max-packets N` makes the command finite. After receiving `N` input datagrams, OrbitOps releases held tail packets, drains scheduled deliveries, writes the final summary, and exits.

## Event logs

`--event-log PATH` creates or replaces a canonical JSONL file. Every line is independently parseable. Complete runs end with `run_summary`; interrupted or failed runs may contain a valid partial stream without a summary.

Event logs contain metadata rather than packet payloads. Ground-station session recordings and link-event logs serve different purposes and should use different files.

Validate a complete event log from Python:

```bash
python - <<'PY'
from pathlib import Path
from orbitops.link import load_link_events, validate_run_summary

statistics = validate_run_summary(load_link_events(Path("sessions/link-events.jsonl")))
print(statistics)
PY
```

## Replay telemetry

```bash
orbitops replay sessions/telemetry.jsonl --speed 4
```

Starting a new recording or link event log at the same path replaces the previous file. Copy important captures before reusing a filename.

## Exit behavior

- `0`: successful command or operator-requested stop;
- `1`: runtime or validated operational failure raised as `SystemExit`;
- `2`: standard command-line parsing failure.

The link runtime translates `SIGINT` and `SIGTERM` into a cooperative stop request, emits a summary for the observed portion of the run, and closes both sockets. Invalid CLI configuration is rejected before bind.

Ground-station packet validation failures are reported without terminating the UDP listener. Invalid replay files terminate replay with an actionable message.

## Troubleshooting

### `Address already in use`

Another process is bound to the selected UDP port. Choose another port or stop the conflicting process. Check both the ground station (`9000` by default) and link listener (`9001` by default).

### Link is ready but no telemetry appears

Confirm the full route:

1. simulator sends to the link listen host and port;
2. link forwards to the ground-station host and port;
3. ground station is already running;
4. local firewall rules permit loopback UDP.

### `CRC mismatch`

The packet was modified or corrupted. This is expected when `--corrupt-rate` selects a packet. CRC-32 detects the change; it does not repair or authenticate the datagram.

### Event log has no `run_summary`

The process was interrupted before its normal shutdown path completed, the storage write failed, or the process was forcibly killed. The partial log remains inspectable, but `validate_run_summary` correctly rejects it as incomplete.

### Fewer forwarded packets than received packets

Check the configured loss rate and final statistics. One duplicated packet creates two deliveries; one dropped packet creates none. Held packets are drained automatically only for finite `--max-packets` runs or normal cooperative shutdown.

### Build cannot find C++ standard headers

Verify the compiler independently with a minimal C++17 program. On macOS, ensure a complete Xcode Command Line Tools installation is selected with `xcode-select`.

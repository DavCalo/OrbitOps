# Operations guide

## Supported environment

- Python 3.11–3.13;
- C++17 compiler;
- CMake 3.20 or newer;
- Linux or macOS. Windows users should use WSL for the simulator.

## Install the ground-station CLI

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

## Run a session

Terminal 1:

```bash
orbitops listen --host 127.0.0.1 --port 9000 --record sessions/demo.jsonl
```

Terminal 2:

```bash
./build/orbitops_sim \
  --host 127.0.0.1 \
  --port 9000 \
  --interval-ms 500 \
  --packets 80 \
  --scenario thermal \
  --drop-every 11
```

Stop an unlimited simulator with `Ctrl+C`. The process handles `SIGINT` and `SIGTERM` and exits after the current cycle.

## Replay

```bash
orbitops replay sessions/demo.jsonl --speed 4
```

Starting a new recording at the same path replaces the previous file. Copy important captures before reusing a filename.

## Exit behavior

- `0`: successful command or operator-requested stop;
- `1`: simulator runtime or argument error;
- `2`: standard command-line parsing error where applicable.

Ground-station validation failures are reported without terminating the UDP listener. Invalid replay files terminate replay with an actionable message.

## Troubleshooting

### `Address already in use`

Another process is bound to the selected UDP port. Choose another port or stop the conflicting process.

### No telemetry appears

Confirm that listener and simulator use the same host and port. Use `127.0.0.1` for the first test and check local firewall rules.

### `CRC mismatch`

The packet was modified or corrupted. This is expected only in future corruption scenarios or when untrusted data reaches the listener.

### Build cannot find C++ standard headers

Verify the compiler independently with a minimal C++17 program. On macOS, ensure a complete Xcode Command Line Tools installation is selected with `xcode-select`.

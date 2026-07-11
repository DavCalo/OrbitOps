#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cat <<TEXT
OrbitOps demo

Repository: $ROOT

Preparation:
  cd "$ROOT"
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install -e .
  make build

Terminal 1 — ground station:
  cd "$ROOT"
  source .venv/bin/activate
  orbitops listen --host 127.0.0.1 --port 9000 --record sessions/demo.jsonl

Terminal 2 — on-board simulator:
  cd "$ROOT"
  ./build/orbitops_sim --host 127.0.0.1 --port 9000 \\
    --interval-ms 500 --packets 80 --scenario thermal --drop-every 11

Replay:
  orbitops replay sessions/demo.jsonl --speed 4
TEXT

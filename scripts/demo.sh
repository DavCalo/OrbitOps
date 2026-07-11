#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cat <<'TEXT'
OrbitOps demo

Open two terminals.

Terminal 1:
  cd REPO
  python3 -m ground_station.orbitops listen --host 127.0.0.1 --port 9000 --record sessions/demo.jsonl

Terminal 2:
  cd REPO
  cmake -S onboard -B build
  cmake --build build
  ./build/orbitops_sim --host 127.0.0.1 --port 9000 --interval-ms 500 --packets 80 --scenario thermal --drop-every 11

Replay:
  python3 -m ground_station.orbitops replay sessions/demo.jsonl --speed 4
TEXT

printf '\nRepository: %s\n' "$ROOT"

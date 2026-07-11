# Contributing to OrbitOps

Thank you for considering a contribution. OrbitOps favors small, reviewable changes with explicit behavior and deterministic tests.

## Development setup

Requirements:

- Python 3.11 or newer;
- CMake 3.20 or newer;
- a C++17 compiler;
- macOS or Linux. Windows is supported through WSL for the on-board simulator.

```bash
python3 -m venv .venv
source .venv/bin/activate
make bootstrap
make verify
```

## Change workflow

1. Open an issue for substantial product, protocol, or architecture changes.
2. Create a focused branch from `main`.
3. Keep runtime dependencies minimal and justify new dependencies.
4. Add or update tests for observable behavior.
5. Update the protocol and architecture documentation when contracts change.
6. Run `make verify` before opening a pull request.

## Engineering expectations

- Preserve deterministic scenarios and tests.
- Treat protocol changes as compatibility-sensitive.
- Keep error messages actionable and avoid swallowing failures.
- Do not weaken CRC, input validation, CI permissions, or security checks without a documented reason.
- Never commit secrets, private telemetry, or generated session recordings.

## Commit messages

Use concise, imperative Conventional Commit-style subjects when practical:

```text
feat: add deterministic link latency
fix: reject unsupported packet flags
docs: document ground-station operations
test: cover sequence wraparound
```

## Pull requests

A pull request should explain:

- the problem;
- the user-visible outcome;
- protocol or CLI compatibility implications;
- tests performed;
- follow-up work that remains out of scope.

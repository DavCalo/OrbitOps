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
2. Create a focused branch from the latest verified `main`.
3. Plan a small number of logical commits when the change has distinct reviewable stages.
4. Keep runtime dependencies minimal and justify new dependencies.
5. Add or update tests in the same logical commit as the behavior they verify.
6. Run targeted checks after each commit and `make verify` once before opening a pull request.
7. Update public documentation and `[Unreleased]` when user-visible behavior or contracts change.
8. Review the complete diff, compatibility impact, security impact, and generated artifacts.

## Engineering expectations

- Preserve deterministic scenarios and tests.
- Treat protocol changes as compatibility-sensitive.
- Keep error messages actionable and avoid swallowing failures.
- Do not weaken CRC, input validation, CI permissions, or security checks without a documented reason.
- Never commit secrets, private telemetry, or generated session recordings.

## Code documentation standard

OrbitOps treats comments and docstrings as part of the maintenance contract.

- Use docstrings for public Python modules, classes, and functions, and for private
  helpers whose contract is not obvious from their name and types.
- Use inline comments to explain rationale, invariants, units, compatibility
  constraints, or deliberate trade-offs.
- Prefer precise names, types, constants, and small functions over comments that
  merely narrate the next statement.
- Replace domain-specific magic numbers with named constants whose names include
  units where practical.
- Keep comments synchronized with behavior; a stale comment is a defect.
- Track unfinished work as `TODO(#issue): ...` or `FIXME(#issue): ...` rather than
  leaving unowned notes in the source.
- Record cross-cutting or compatibility-sensitive decisions in an ADR.

## Commit messages

Use concise, imperative Conventional Commit-style subjects when practical:

```text
feat: add deterministic link latency
fix: reject unsupported packet flags
docs: document ground-station operations
test: cover sequence wraparound
```

A pull request may contain a few logical commits when that improves reviewability. Each commit
should have one recognizable purpose, include its relevant tests, and leave the affected
subsystem in a valid state. Avoid `WIP`, `fix tests`, `misc`, and other diary-style subjects.

OrbitOps uses squash merge for feature pull requests. The pull-request title becomes the commit
subject on `main`, and GitHub adds the pull-request number. Do not add `(#PR)` manually to local
commit subjects or pull-request titles.

## Pull requests

A pull request should explain:

- the problem and user-visible outcome;
- scope and explicit non-goals;
- protocol, schema, CLI, platform, and security implications;
- targeted validation and the complete `make verify` result;
- documentation and changelog updates;
- follow-up work that remains out of scope.

Before merge, all required CI checks must pass, review conversations must be resolved, the head
commit must match the reviewed diff, and the branch must contain no generated or unrelated files.

# Parser hardening

OrbitOps treats every packet, imported JSONL record, and TOML document as untrusted input.
This document defines the deterministic parser-assurance layer introduced for v0.4.0.

## Covered contracts

The normal CI suite now exercises malformed input for:

- the fixed-width binary telemetry packet decoder;
- telemetry recording and replay JSONL;
- link-event JSONL;
- alarm-event JSONL;
- mission-profile TOML;
- alarm-policy TOML.

The binary protocol is tested through complete truncation sets, bounded extensions, and one
deterministic single-bit mutation per byte. Structured documents are tested for missing and
unknown keys, wrong top-level types, invalid versions, non-finite numbers, malformed text,
and compatibility-preserving canonical round trips.

## Curated corpus

Regression inputs live under `tests/fixtures/parser_corpus`. Each fixture is intentionally
small, contains no private telemetry or credentials, and represents one stable failure class.
Discovered parser defects must be minimized and added to this corpus before they are fixed.

The initial corpus records a telemetry-replay weakness that previously accepted unknown keys,
boolean version values, and non-finite timestamps. The replay parser now requires an exact
record shape and strict scalar types while preserving the version-1 recording format.

## Deterministic mutations

`tests/parser_mutations.py` contains bounded mutation helpers. They avoid platform entropy,
network access, randomized seeds, and unbounded input generation. Identical source data
therefore produces identical cases on Python 3.11 through 3.13 and on Linux and macOS.

## Failure requirements

A malformed input must produce a bounded `ValueError`, `TypeError`, or protocol-specific
validation error. Crashes, hangs, uncontrolled allocation, silent key acceptance, and partial
schema coercion are failures.

## Future continuous fuzzing

Continuous coverage-guided fuzzing is intentionally separate from the normal CI budget.
A future integration may use a dedicated service or scheduled workflow, but every discovered
failure must first be minimized into a deterministic corpus fixture so the standard pull-request
suite remains reproducible and fast.

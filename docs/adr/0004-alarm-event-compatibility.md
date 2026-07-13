# ADR 0004: Alarm-event compatibility and audit boundaries

## Status

Accepted for OrbitOps v0.4.0.

## Context

The alarm engine now emits explicit lifecycle transitions and alarm policies have stable
effective fingerprints. Operators need a machine-readable record of those decisions without
changing the telemetry recording format or requiring consumers to re-evaluate historical
packets against a possibly different policy.

Alarm-event logs must also remain useful after cooperative interruption, reject malformed
imported data, and make compatibility changes explicit.

## Decision

OrbitOps defines alarm-event JSONL as a separate compatibility contract beginning at schema
version `1`.

A complete stream contains:

1. one leading `run_metadata` record;
2. zero or more `alarm_raised`, `alarm_updated`, and `alarm_cleared` records;
3. one final `run_summary`.

Metadata records the effective policy name, original local reference, policy schema version,
and SHA-256 fingerprint. Transition records preserve packet sequence, stable alarm identity,
presentation code, severity, message, observed value, and threshold.

Readers validate exact key sets, scalar types, finite numeric values, contiguous indices,
monotonic elapsed time, stable session identity, metadata placement, and summary placement.
Complete logs are accepted only when summary counters match an independent recomputation.

A cooperatively interrupted run writes a summary while unwinding the listener context. A file
interrupted before that point may omit the summary and remains inspectable as a partial run.

### Compatibility rules

- telemetry recordings, link events, and alarm events remain separate files and schemas;
- the binary packet and telemetry recording formats are unchanged;
- alarm-event schema `1` readers reject unknown top-level and attribute keys;
- adding or changing required record meaning requires a new alarm-event schema version;
- presentation messages are retained for operators but are not stable machine identities;
- `alarm_identity`, `event_type`, and documented attribute names are the machine contract;
- policy fingerprints identify equivalent effective behavior but do not authenticate a run;
- local policy references may expose paths and must not contain secrets.

Alarm logs contain decoded operational metadata only. Raw telemetry packet bytes remain in the
separate telemetry recording when explicitly requested.

## Consequences

- historical alarm decisions can be inspected without re-running policy evaluation;
- consumers can independently verify ordering and transition counters;
- partial logs remain useful without being mistaken for complete runs;
- strict readers prevent silent schema drift;
- future schema evolution must be explicit and versioned;
- provenance, authenticity, encryption, and signed manifests remain outside this contract.

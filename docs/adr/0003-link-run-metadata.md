# ADR 0003: Link run metadata and event schema version 2

- Status: Accepted
- Date: 2026-07-12

## Context

Mission profiles make link configuration reusable, but a packet-event stream containing only impairment decisions and final counters cannot identify which effective configuration produced those decisions. Logging only a profile name is insufficient because explicit CLI options can override profile values. Logging the full configuration in every record would duplicate data and expand metadata exposure.

OrbitOps also needs to preserve the meaning of existing packet events and summary counters and continue reading v0.2 logs.

## Decision

OrbitOps will:

1. move canonical effective-link configuration fingerprinting into the link package while retaining profile compatibility exports;
2. emit link-event schema version `2` for new runs;
3. emit exactly one `run_metadata` event as event index `0`;
4. record the effective configuration SHA-256 fingerprint in that event;
5. record profile name, original reference, and profile schema version when a profile is selected;
6. set all profile fields to `null` for no-profile runs;
7. leave existing packet-event attributes and `run_summary` counters unchanged;
8. continue loading and validating schema-version-1 logs;
9. reject mixed-version streams and malformed version-2 metadata order.

The runtime verifies that supplied run metadata contains the fingerprint of the effective `LinkConfig`.

## Consequences

### Positive

- every new event log identifies its effective configuration;
- profile plus override runs are distinguishable;
- summary counter semantics remain stable;
- metadata is emitted even for empty or interrupted runs;
- legacy v0.2 logs remain inspectable;
- one metadata record avoids per-event duplication.

### Negative

- older OrbitOps versions cannot parse schema-version-2 logs;
- external profile references may reveal local path information;
- SHA-256 fingerprints can be recomputed after tampering and do not prove authenticity.

## Alternatives considered

### Add metadata fields to every event

Rejected because it duplicates identical values and increases file size and disclosure.

### Put metadata inside `run_summary`

Rejected because interrupted runs could lose configuration identity and existing summary attributes would no longer be counter-only.

### Keep schema version 1 and add an event type

Rejected because older schema-version-1 consumers would fail on an undocumented additive event. Advancing the schema makes the compatibility boundary explicit.

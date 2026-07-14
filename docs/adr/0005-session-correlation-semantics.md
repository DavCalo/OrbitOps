# ADR 0005: Unified session correlation semantics

## Status

Accepted for OrbitOps v0.5.0.

## Context

OrbitOps persists three independent evidence streams:

1. telemetry recording schema version `1` stores raw packet bytes and a ground-receiver
   `received_at` wall-clock timestamp;
2. link-event schema versions `1` and `2` store source-local `event_index`, `elapsed_ns`,
   `session_id`, and `packet_index` values but exclude datagram payloads;
3. alarm-event schema version `1` stores source-local `event_index`, `elapsed_ns`, `session_id`,
   and lifecycle-transition `packet_sequence` values but excludes raw packet bytes.

The v0.5.0 inspector must present these streams together without concatenating their schemas,
inventing a common clock, or claiming packet and run relationships that the evidence cannot
prove.

## Decision

OrbitOps keeps the three existing formats unchanged. Unified inspection validates each source
through its existing strict loader and builds an operator-selected evidence bundle. Selection of
files is not provenance proof: the report must state that cross-stream run identity is unverified
unless a future version introduces an explicit binding mechanism.

A new versioned session manifest is **not required for v0.5.0**. Safe inspection is possible
without one when uncertain relationships remain visible instead of being guessed. A manifest may
be introduced later only if a concrete requirement needs cross-stream identity, clock-domain
mapping, hashes, signatures, or provenance guarantees.

### Contract matrix

| Property | Telemetry recording v1 | Link events v1/v2 | Alarm events v1 | Cross-stream rule |
|---|---|---|---|---|
| Canonical source order | JSONL record order | `event_index` | `event_index` | Preserve source-local order |
| Run identity | none | `session_id` | `session_id` | IDs use independent namespaces and are not compared across lanes |
| Packet reference | decoded `sequence` | `packet_index` | `packet_sequence` | Only telemetry/alarm sequence equality can support packet correlation |
| Producer time | decoded `timestamp_ms` wall clock | none | none | Display only; no synchronization guarantee |
| Receiver time | `received_at` wall clock | none | none | Display only; not a shared clock |
| Relative time | none | process-local `elapsed_ns` | process-local `elapsed_ns` | Never merge into a common timeline |
| Completion marker | none | final `run_summary` | final `run_summary` | Link/alarm summary presence determines completeness for that lane |
| Raw payload | full packet bytes | excluded | excluded | Do not copy raw bytes into derived link or alarm entries |
| Configuration identity | none | link fingerprint and optional profile metadata in v2 | policy fingerprint and identity | Report independently; do not infer compatibility between unrelated metadata |

### Correlation classifications

#### Telemetry and alarm events

An alarm transition can correlate to telemetry by packet sequence only:

- **exact**: exactly one loaded telemetry record decodes to the transition's
  `packet_sequence`;
- **ambiguous**: more than one telemetry record has that sequence, including duplicates or
  sequence wraparound;
- **impossible from loaded evidence**: no loaded telemetry record has that sequence.

Sequence equality proves a field-level relationship within the operator-selected bundle. It does
not prove that separately supplied files originated from the same physical or simulated run.

#### Link events and other lanes

`packet_index` is the deterministic index of a datagram accepted by the link runtime. It is not a
telemetry sequence number. Link events therefore remain a **separate lane** even when a numeric
`packet_index` happens to equal a telemetry or alarm sequence.

Link-event `packet_index` values may group link events belonging to the same input datagram within
one validated link stream. They do not establish cross-stream packet identity.

#### Source-local ordering

Source-local record order is authoritative. For deterministic presentation when entries otherwise
lack a shared ordering key, lane precedence is:

1. telemetry;
2. alarm;
3. link.

This precedence is a formatting rule only. It does not claim causal or temporal order between
processes.

### Input-state rules

- A telemetry file with fully parseable records is structurally valid. Because recording schema
  version `1` has no metadata or summary, it cannot prove whether capture ended cooperatively.
- A link or alarm stream with a valid final summary is complete for that source.
- A structurally valid link or alarm stream without a summary is incomplete but inspectable.
- An empty source produces an explicit incomplete/no-evidence diagnostic rather than a successful
  complete session.
- Malformed JSON, unsupported versions, mixed session IDs within one event stream, non-contiguous
  event indices, backwards elapsed time, invalid metadata placement, and invalid summaries remain
  hard source-validation failures.
- Different link and alarm `session_id` values are not a mismatch because the existing producers
  allocate them independently.
- Legacy link-event schema version `1` remains readable and is reported without run metadata.

## Consequences

- The v0.5.0 inspector can provide deterministic correlated evidence without changing existing
  recording or event schemas.
- Telemetry/alarm matches remain exact only for a unique packet sequence in the loaded telemetry
  evidence.
- Duplicates, wraparound, missing packets, unrelated files, and incomplete streams remain visible
  as ambiguity or diagnostics.
- Link evidence remains useful for impairment and delivery analysis without a fabricated packet
  mapping.
- Cross-process elapsed times and wall clocks are never normalized into a false global clock.
- The report is operational evidence, not authentication, provenance, or proof that every input
  belongs to one run.
- Future manifests, signatures, synchronized clocks, or payload hashes require a separate
  versioned design decision.

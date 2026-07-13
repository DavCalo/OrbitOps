# Alarm-event schema

OrbitOps alarm logs are canonical, line-delimited JSON streams that record policy identity,
explicit alarm-lifecycle transitions, and independently verifiable run counters.

The current alarm-event schema version is `1`.

Alarm logs are a separate compatibility contract from telemetry recordings, link-event logs,
mission profiles, alarm policies, and the binary telemetry protocol.

## Stream order

A complete stream contains:

1. exactly one leading `run_metadata` event;
2. zero or more `alarm_raised`, `alarm_updated`, and `alarm_cleared` events;
3. exactly one final `run_summary` event.

An interrupted file may omit `run_summary`. Such a file remains structurally inspectable, but
it is not considered a complete run and cannot pass summary validation.

Every record contains exactly these top-level keys:

```json
{
  "attributes": {},
  "elapsed_ns": 0,
  "event_index": 0,
  "event_type": "run_metadata",
  "packet_sequence": null,
  "schema_version": 1,
  "session_id": "alarm-..."
}
```

`event_index` starts at zero and is contiguous. `elapsed_ns` is monotonic relative time from
the start of the alarm log. All records in one file use the same non-empty `session_id`.

## Run metadata

`run_metadata` must be the first event and has a null `packet_sequence`.

Its attributes are:

```json
{
  "policy_fingerprint": "sha256:<64 lowercase hexadecimal digits>",
  "policy_name": "thermal-demo",
  "policy_reference": "builtin:thermal-demo",
  "policy_schema_version": 1
}
```

The fingerprint identifies the canonical behavior-affecting policy configuration. It is a
reproducibility identifier, not a signature, authenticity proof, or provenance guarantee.

`policy_reference` preserves the operator-provided local reference. Local paths may expose
host or directory names and must not contain credentials or other secrets.

## Lifecycle transitions

Transition event types are:

- `alarm_raised`;
- `alarm_updated`;
- `alarm_cleared`.

Each transition has an unsigned 32-bit `packet_sequence` and exactly these attributes:

```json
{
  "alarm_identity": "temperature",
  "code": "HIGH_TEMPERATURE",
  "message": "temperature is 61.00 °C",
  "observed_value": 61.0,
  "severity": "critical",
  "threshold": 38.0
}
```

`alarm_identity` is stable across lifecycle changes. `code` and `severity` describe the
presentation associated with that specific transition. `observed_value` may be a finite
number, string, or null. `threshold` is a finite number or null.

Sequence-gap alarms are point-in-time `alarm_raised` events. Stateful temperature, battery,
and SAFE-mode alarms may produce raised, updated, and cleared events according to the alarm
engine and selected policy.

## Run summary

A complete stream ends with `run_summary`, with null `packet_sequence` and these attributes:

```json
{
  "transitions_cleared": 0,
  "transitions_raised": 2,
  "transitions_total": 3,
  "transitions_updated": 1
}
```

Readers must recompute transition counts from preceding records and reject summaries that do
not match. Metadata and summary records do not contribute to transition counters.

## Canonical encoding

OrbitOps writes compact JSON with lexicographically sorted keys and one record per line.
Readers validate exact key sets, scalar value types, finite floating-point values, contiguous
indices, stable session identity, monotonic elapsed time, metadata placement, and summary
placement.

Blank lines are ignored while reading. Unknown keys, unsupported schema versions, malformed
JSON, mixed sessions, non-contiguous indices, and records after a summary are rejected.

## Data and security boundary

Alarm logs contain decoded operational metadata and human-readable transition messages. They
do not contain raw telemetry packet bytes.

They are still untrusted imported data. Consumers must use the OrbitOps loader rather than
assuming that a `.jsonl` extension implies valid structure. Logs may expose policy names,
operator-selected references, session identifiers, telemetry sequence numbers, and observed
operational values.

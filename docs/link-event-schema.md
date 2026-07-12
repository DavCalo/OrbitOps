# OrbitOps link event schema

OrbitOps records link-emulator behavior as newline-delimited JSON (JSONL). Each line is one independent event object. The format supports incremental inspection, deterministic ordering, partial-run recovery, and automated counter verification.

New OrbitOps v0.3 runs emit schema version `2`. Schema version `1` logs produced by OrbitOps v0.2 remain readable and verifiable.

## Compatibility decision

Schema version `2` adds one leading `run_metadata` event. Existing packet, impairment, scheduling, forwarding, reorder, and `run_summary` records keep the same top-level fields and event-specific attributes.

The compatibility rules are:

- version `1` streams contain no `run_metadata` event;
- version `2` streams begin with exactly one `run_metadata` event;
- one stream uses one schema version and one session identifier;
- existing summary counter names and meanings are unchanged;
- `load_link_events` reads versions `1` and `2`;
- OrbitOps emits version `2` for new runs.

The decision is also recorded in [`adr/0003-link-run-metadata.md`](adr/0003-link-run-metadata.md).

## Canonical record shape

Every record uses the same top-level shape:

```json
{
  "attributes": {
    "payload_bytes": 35
  },
  "elapsed_ns": 1275000,
  "event_index": 1,
  "event_type": "packet_received",
  "packet_index": 0,
  "schema_version": 2,
  "session_id": "demo-session"
}
```

| Field | Type | Description |
|---|---|---|
| `schema_version` | integer | Link-event schema version: `1` or `2`. |
| `session_id` | string | Non-empty identifier shared by all records in a run. |
| `event_index` | integer | Zero-based contiguous order within the run. |
| `elapsed_ns` | integer | Monotonic nanoseconds elapsed since runtime start. |
| `event_type` | string | Stable event name documented below. |
| `packet_index` | integer or `null` | Deterministic input-packet index when applicable. |
| `attributes` | object | Event-specific scalar metadata. |

Attribute values are limited to strings, integers, finite floats, booleans, and `null`. Nested arrays and objects are not part of the current schema.

## `run_metadata`

Schema-version-2 streams begin with:

```json
{
  "attributes": {
    "configuration_fingerprint": "sha256:5a0f...",
    "profile_name": "intermittent-loss",
    "profile_reference": "intermittent-loss",
    "profile_schema_version": 1
  },
  "elapsed_ns": 0,
  "event_index": 0,
  "event_type": "run_metadata",
  "packet_index": null,
  "schema_version": 2,
  "session_id": "mission-profile-demo"
}
```

Attributes:

- `configuration_fingerprint`: SHA-256 fingerprint of the effective `LinkConfig` after all overrides;
- `profile_name`: resolved profile name, or `null` when no profile was selected;
- `profile_reference`: original CLI reference, or `null`;
- `profile_schema_version`: selected profile schema version, or `null`.

The three profile fields are either all populated or all `null`. A profile name does not replace the fingerprint: explicit CLI options may change the effective configuration after profile loading.

The fingerprint is deterministic reproducibility evidence. It is not a MAC, signature, provenance proof, or protection against log modification.

## Packet and delivery event types

### `packet_received`

Emitted once for every accepted input datagram.

Attributes: `payload_bytes`.

### `packet_dropped`

Emitted when the impairment engine discards an input packet.

Attributes: `payload_bytes`.

### `packet_delayed`

Emitted when a non-dropped packet receives a positive effective delay.

Attributes: `delay_ms`.

### `packet_duplicated`

Emitted when one input packet creates two scheduled deliveries.

Attributes: `copies`.

### `packet_corrupted`

Emitted when one deterministic bit is flipped.

Attributes: `corrupted_bit`.

### `delivery_scheduled`

Emitted once per delivery, including duplicate copies.

Attributes:

- `copy_index`;
- `corrupted_bit`;
- `delay_ms`;
- `hold_packets`;
- `payload_bytes`.

### `packet_reordered`

Emitted once when a packet is actually forwarded after a newer packet.

Attributes:

- `overtaken_by_packet_index`;
- `release_after_packet`.

### `packet_forwarded`

Emitted after a complete UDP datagram is sent downstream.

Attributes:

- `copy_index`;
- `corrupted_bit`;
- `payload_bytes`.

## `run_summary`

The final event of a complete run. Its `packet_index` is `null`. Attributes remain exactly:

- `packets_received`;
- `packets_dropped`;
- `packets_delayed`;
- `packets_duplicated`;
- `packets_corrupted`;
- `packets_reordered`;
- `deliveries_scheduled`;
- `deliveries_forwarded`.

A summary is valid only when each counter matches the corresponding preceding packet or delivery events. `run_metadata` does not contribute to any counter.

## Ordering rules

For schema version `2`:

1. `run_metadata` is event index `0`;
2. packet and delivery events follow in stable runtime order;
3. `elapsed_ns` never decreases;
4. all records use one `session_id` and schema version;
5. `run_summary`, when present, is final.

A partial version-2 log containing only `run_metadata`, or metadata plus packet events, remains structurally readable. A complete stream is required for summary validation.

## Reading logs

```python
from pathlib import Path

from orbitops.link import (
    load_link_events,
    run_metadata_from_events,
    validate_run_summary,
)

events = load_link_events(Path("sessions/link-events.jsonl"))
metadata = run_metadata_from_events(events)
statistics = validate_run_summary(events)

print(metadata)
print(statistics)
```

`run_metadata_from_events` returns `None` for a valid legacy schema-version-1 stream.

## Security and privacy

- Logs contain metadata, not raw datagram payloads.
- `profile_reference` may reveal a local path or operator naming convention.
- Session identifiers and profile references must not contain secrets.
- Plaintext logs can be edited; structural validation does not prove authenticity.
- Imported JSONL is untrusted input and is validated before use.
- Retention and operating-system file permissions remain operator responsibilities.

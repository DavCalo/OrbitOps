# OrbitOps link event schema

OrbitOps records link-emulator behavior as **newline-delimited JSON (JSONL)**. Each line is one independent event object. The format is designed for deterministic ordering, incremental inspection, replay, and automated verification.

The schema described here is version `1`.

## Design goals

- every receive, impairment decision, scheduling decision, and successful forward can be observed;
- event order is explicit through a contiguous `event_index`;
- all times are relative to one runtime session and use monotonic nanoseconds;
- interrupted runs remain readable even when no final summary exists;
- complete runs end with a summary whose counters can be independently recomputed;
- event files do not contain raw packet payloads.

## Canonical record

```json
{
  "attributes": {
    "payload_bytes": 35
  },
  "elapsed_ns": 1275000,
  "event_index": 0,
  "event_type": "packet_received",
  "packet_index": 0,
  "schema_version": 1,
  "session_id": "demo-session"
}
```

Fields:

| Field | Type | Description |
|---|---|---|
| `schema_version` | integer | Event schema version. Version `1` is currently supported. |
| `session_id` | string | Non-empty identifier shared by all events in one run. |
| `event_index` | integer | Zero-based contiguous event order within the session. |
| `elapsed_ns` | integer | Monotonic nanoseconds elapsed since the runtime started. |
| `event_type` | string | Stable event name listed below. |
| `packet_index` | integer or `null` | Deterministic input-packet index, when applicable. |
| `attributes` | object | Event-specific scalar metadata. |

`attributes` values are limited to strings, integers, finite floating-point numbers, booleans, and `null`. Nested objects and arrays are not used in schema version `1`.

## Event types

### `packet_received`

Emitted once for every input datagram accepted by the runtime.

Attributes:

- `payload_bytes`

### `packet_dropped`

Emitted when the impairment engine discards an input packet. No delivery events are produced for that packet.

Attributes:

- `payload_bytes`

### `packet_delayed`

Emitted once when a non-dropped packet receives a positive delay after fixed latency and jitter are combined.

Attributes:

- `delay_ms`

### `packet_duplicated`

Emitted once when one input packet produces two scheduled deliveries.

Attributes:

- `copies`

### `packet_corrupted`

Emitted once when the output payload has one deterministic bit flipped.

Attributes:

- `corrupted_bit`

### `delivery_scheduled`

Emitted once per delivery, including duplicate copies.

Attributes:

- `copy_index`
- `corrupted_bit`
- `delay_ms`
- `hold_packets`
- `payload_bytes`

A positive `hold_packets` records the bounded-reordering decision even if the stream ends before a later packet overtakes it.

### `packet_reordered`

Emitted once per packet only when that packet is **actually forwarded after a newer packet**. It therefore represents observable reordering, not merely a hold decision.

Attributes:

- `overtaken_by_packet_index`
- `release_after_packet`

### `packet_forwarded`

Emitted after a complete UDP datagram has been successfully sent to the configured downstream endpoint.

Attributes:

- `copy_index`
- `corrupted_bit`
- `payload_bytes`

### `run_summary`

The final event of a complete run. Its `packet_index` is `null`. The attributes contain counters derived from all preceding events:

- `packets_received`
- `packets_dropped`
- `packets_delayed`
- `packets_duplicated`
- `packets_corrupted`
- `packets_reordered`
- `deliveries_scheduled`
- `deliveries_forwarded`

A summary is valid only when each counter exactly matches the corresponding emitted events.

## Ordering and determinism

Within one run:

1. `event_index` starts at `0` and increases by one;
2. `elapsed_ns` never decreases;
3. all events use the same `session_id`;
4. events for one packet are emitted in a stable order;
5. scheduled deliveries use the scheduler order: deadline, packet index, then copy index;
6. `run_summary`, when present, is the final event.

The impairment decisions are deterministic for a fixed seed, configuration, and packet stream. Live `elapsed_ns` values and an automatically generated session identifier are operational metadata and are not part of that decision contract. Callers can provide an explicit `session_id` and injected clock for reproducible tests.

## Writing and reading logs

```python
from pathlib import Path

from orbitops.link import JsonlEventRecorder, LinkConfig, LinkRuntime

with JsonlEventRecorder(Path("sessions/link-events.jsonl")) as recorder:
    runtime = LinkRuntime(
        ("127.0.0.1", 9001),
        ("127.0.0.1", 9000),
        LinkConfig(seed=42, loss_rate=0.05),
        event_sink=recorder.write,
        session_id="demo-001",
    )
    runtime.open()
    runtime.run()
```

Replay and validate a complete file:

```python
from pathlib import Path

from orbitops.link import load_link_events, validate_run_summary

events = load_link_events(Path("sessions/link-events.jsonl"))
statistics = validate_run_summary(events)
```

`load_link_events` accepts a structurally valid partial log without a summary, allowing interrupted runs to be inspected. `validate_run_summary` requires a complete run and verifies all counters.

## Security and privacy notes

- Event logs contain metadata, not raw datagram payloads.
- Session identifiers are operator-controlled and should not contain secrets.
- File paths and retention policies remain the responsibility of the caller.
- JSONL logs are untrusted input when imported; OrbitOps validates their structure and schema version before use.

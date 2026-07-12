# ADR 0001: Deterministic link-emulator semantics

- **Status:** Accepted
- **Date:** 2026-07-12
- **Target:** OrbitOps v0.2.0
- **Parent epic:** #4

## Context

OrbitOps needs a network-impairment layer that is reproducible in local demos,
CI, and future incident-style replays. The first increment intentionally excludes
UDP sockets and scheduling. It defines a pure transformation from one ordered
input datagram to one immutable outcome.

Using Python's global random state, wall-clock time, or platform-specific APIs
would make failures difficult to reproduce. The core therefore owns a small,
explicit pseudo-random algorithm and consumes a fixed number of samples for every
input packet.

## Decision

### Input order

Every datagram passed to `ImpairmentEngine.process()` receives a monotonically
increasing zero-based `packet_index`. Input order is part of the deterministic
contract.

### Generator

The engine uses SplitMix64 with unsigned 64-bit wrap-around. The algorithm and
constants live in `link/decisions.py` and are protected by a golden-vector test.
This is a simulation primitive, not a cryptographic generator.

Exactly six 64-bit values are consumed for every input packet, in this order:

1. packet-loss decision;
2. duplication decision;
3. corruption decision;
4. jitter value;
5. reorder hold count;
6. corruption-bit selection.

Samples are consumed even if an earlier decision, such as loss, makes later
results unobservable. Consequently, unrelated configuration changes do not shift
the pseudo-random stream for subsequent packets.

### Probability mapping

Rates are inclusive values from `0.0` to `1.0`. A sample is compared with an
integer threshold over the full 64-bit domain. Zero never selects an impairment;
one always selects it.

### Delay

Effective delay is:

```text
max(0, latency_ms + uniform_integer(-jitter_ms, +jitter_ms))
```

The jitter interval is inclusive. Scaling uses integer multiply-high mapping so
one pseudo-random draw always produces one bounded value.

### Reordering

The pure core does not reorder packets itself. It emits `hold_packets`, an integer
from zero through `reorder_window`. The runtime scheduler introduced in a later
increment will hold the datagram until at most that many newer packets have
arrived. A zero window disables reordering.

### Duplication

Duplication produces at most one additional delivery. Both deliveries carry the
same payload, delay, hold count, and corruption metadata, and are distinguished
by `copy_index` values zero and one. Runtime ordering for tied deliveries must use
`copy_index` as the stable tie-breaker.

### Corruption

Corruption flips exactly one bit in a non-empty payload. Bit zero is the
least-significant bit of byte zero. The selected bit index is included in every
resulting delivery. Empty payloads remain unchanged and report no corrupted bit.

### Loss precedence

Loss suppresses every delivery, including a selected duplicate or corruption.
The hidden pseudo-random decisions are still consumed but are not exposed as
performed impairments.

### No-op configuration

The default configuration emits exactly one byte-for-byte-identical delivery
with zero delay, zero packet hold, and no corruption metadata.

## Consequences

### Positive

- The core is independent of sockets, time, threads, and external packages.
- Identical seed, configuration, and ordered input stream yield identical output.
- Golden decisions can detect accidental compatibility changes.
- The future runtime can focus on scheduling and I/O rather than impairment logic.

### Trade-offs

- SplitMix64 is suitable for simulation but not security-sensitive randomness.
- Integer scaling has a negligible distribution bias for bounds that do not divide
  the 64-bit domain exactly.
- `hold_packets` models bounded packet-order disturbance, not an RF channel.
- The engine does not currently model bandwidth, burst-loss states, or correlated
  noise.

## Compatibility policy

Changing the generator, draw order, probability mapping, bit numbering, or golden
combined decisions is a compatibility change. Such a change requires a new ADR,
updated golden vectors, and a changelog entry.

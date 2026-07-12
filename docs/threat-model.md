# Threat model

## Purpose

OrbitOps is a local telemetry simulator, not flight software or a secure communications product. This document makes current trust assumptions explicit so the project is not deployed beyond its intended boundary.

## Assets

- integrity of decoded telemetry;
- integrity of telemetry recordings and link-event logs;
- availability of the simulator, link emulator, and ground station;
- correctness and reproducibility of protocol, impairment, scheduling, and alarm behavior;
- source-code and CI supply-chain integrity.

## Trust boundaries

```text
On-board simulator -> UDP -> link emulator -> UDP -> ground station
                              |                    |
                              v                    v
                         link-event JSONL     telemetry JSONL
```

Both UDP boundaries are untrusted. Imported telemetry recordings and link-event logs are also untrusted input. The link emulator is an explicit fault-injection component, not a security gateway.

## Current controls

- exact packet-length validation;
- protocol magic and version checks;
- reserved-flags validation;
- CRC-32 accidental-corruption detection;
- bounded fixed-width decoding;
- rejection of invalid spacecraft modes;
- pre-socket validation of link ports, rates, seeds, timing values, and reorder windows;
- deterministic and bounded impairment decisions;
- monotonic scheduler inputs and stable delivery ordering;
- versioned telemetry and link-event JSONL formats;
- strict link-event structure, ordering, and summary validation;
- no raw datagram payloads in link-event logs;
- read-only default GitHub Actions permissions;
- pinned GitHub Actions revisions;
- CI tests, type checks, compiler warnings, and sanitizers.

## Known limitations

- UDP traffic is not authenticated or encrypted;
- CRC-32 detects accidental corruption but is not a cryptographic integrity mechanism;
- senders are not authorized or rate-limited;
- the receiver and link emulator have no application-level replay protection;
- telemetry recordings and event logs are plaintext;
- event metadata can still reveal packet timing, sizes, session identifiers, and impairment behavior;
- operator-provided session identifiers may accidentally contain sensitive information;
- the simulator uses host wall-clock time;
- denial-of-service resilience is not a project goal;
- event logs are flushed per event for inspectability, not optimized for hostile high-rate traffic;
- forced process termination can leave a partial log without a final summary.

## Abuse cases

### Datagram injection

An untrusted process can send malformed or fabricated UDP datagrams to either listener. Protocol validation protects the ground decoder from malformed packets but does not authenticate the sender.

### Resource exhaustion

A sender can generate high packet rates, large UDP datagrams, or long-running sessions. OrbitOps bounds individual datagram size and impairment values but does not implement global rate limits, quotas, or storage retention.

### Misleading fault evidence

A user can alter a JSONL log after creation. Structural and summary validation detects internal inconsistency but does not provide provenance or cryptographic authenticity.

### Unsafe network exposure

Binding to a non-loopback address expands the trust boundary. The project does not add transport encryption, identity, or authorization merely because a host argument permits broader binding.

## Safe deployment boundary

Use loopback addresses or a trusted isolated development network. Do not transmit secrets, personal data, proprietary telemetry, or safety-critical commands. Do not expose either UDP listener directly to the public internet.

Store event and telemetry files with operating-system permissions appropriate to their metadata. Use non-sensitive session identifiers and define a retention policy for generated captures.

## Future security work

- authenticated command and telemetry envelopes;
- optional transport encryption;
- sender allowlists and rate limiting;
- replay-window enforcement;
- fuzzing of packet, CLI, telemetry-recording, and link-event parsers;
- signed event manifests or provenance where justified;
- signed release artifacts and build provenance.

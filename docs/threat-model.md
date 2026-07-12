# Threat model

## Purpose

OrbitOps is a local telemetry and deterministic-fault simulator. It is not flight software, a secure communications product, an RF propagation model, or a safety-certified system.

## Assets

- integrity of decoded telemetry;
- integrity of mission-profile files, telemetry recordings, and link-event logs;
- availability of the simulator, link emulator, and ground station;
- reproducibility of configuration resolution, fingerprinting, impairment, scheduling, and alarms;
- source-code, package-resource, and CI supply-chain integrity.

## Trust boundaries

```text
mission profile -> resolver
                     |
simulator -> UDP -> link emulator -> UDP -> ground station
                     |                    |
                     v                    v
             link-event JSONL      telemetry JSONL
```

Both UDP boundaries are untrusted. External mission profiles and imported JSONL files are untrusted input. The link emulator is a fault-injection component, not a security gateway.

## Current controls

- strict TOML parsing with unknown-key and schema-version rejection;
- package-resource allowlist for built-in profiles;
- no remote profile downloads, interpolation, executable hooks, or credentials;
- pre-socket and pre-log profile/configuration validation;
- canonical effective-configuration encoding and deterministic SHA-256 fingerprints;
- exact packet-length, magic, version, flags, mode, and CRC validation;
- bounded fixed-width decoding and bounded impairment values;
- deterministic SplitMix64 decisions and monotonic scheduling;
- link-event schema-version, ordering, metadata, and summary validation;
- legacy schema-version-1 event reading;
- no raw datagram payloads in link-event logs;
- read-only default GitHub Actions permissions and pinned Action revisions;
- CI tests, strict typing, coverage, compiler warnings, sanitizers, package tests, and installed-CLI demos.

## Known limitations

- UDP traffic is unauthenticated and unencrypted;
- CRC-32 is not a cryptographic integrity mechanism;
- configuration fingerprints are not signatures, MACs, or provenance proofs;
- plaintext profiles and logs can be modified by anyone with file access;
- senders are not authorized or rate-limited;
- replay protection is not implemented;
- event metadata reveals timing, sizes, session identifiers, impairment behavior, and profile identity;
- external `profile_reference` values may reveal local paths;
- operator-provided names and session identifiers may contain sensitive information;
- denial-of-service resilience is not a project goal;
- forced termination can leave partial logs.

## Abuse cases

### Malicious or malformed profile

An attacker can provide invalid TOML, unsupported schema versions, extreme values, ambiguous references, or unexpected keys. OrbitOps rejects these before creating an event log or opening a socket.

A valid profile can still request disruptive but bounded behavior such as complete packet loss or high latency. Profiles express simulation behavior; they are not authorization policy.

### Misleading run evidence

A user can edit a profile or JSONL log and recompute a matching fingerprint. Fingerprints identify effective configuration equivalence but do not prove who created a run or whether a log is original.

### Metadata disclosure

A profile path or session identifier can reveal usernames, directories, project names, or operational conventions. Do not include secrets or sensitive customer/mission identifiers.

### Datagram injection

An untrusted process can send malformed or fabricated UDP datagrams. Protocol checks protect parser correctness but do not authenticate the sender.

### Resource exhaustion

A sender can generate high packet rates or long-running sessions. OrbitOps bounds individual datagrams and configuration values but does not enforce global quotas, rate limits, or retention.

### Unsafe network exposure

Binding beyond loopback expands the trust boundary without adding encryption, authorization, or sender identity.

## Safe deployment boundary

Use loopback addresses or a trusted isolated development network. Do not transmit secrets, personal data, proprietary flight telemetry, or safety-critical commands. Do not expose either UDP listener directly to the public internet.

Review external profile files before use. Store profiles and logs with appropriate operating-system permissions, use non-sensitive identifiers, and define a retention policy.

## Future security work

- authenticated command and telemetry envelopes;
- optional transport encryption;
- sender allowlists and rate limiting;
- replay-window enforcement;
- fuzzing of profile, packet, CLI, telemetry, and link-event parsers;
- signed run manifests or attestations where provenance is required;
- signed release artifacts and build provenance.

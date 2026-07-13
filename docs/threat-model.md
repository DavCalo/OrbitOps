# Threat model

## Purpose

OrbitOps is a local telemetry and deterministic-fault simulator. It is not flight software, a
secure communications product, an RF propagation model, or a safety-certified system.

## Assets

- integrity of decoded telemetry and alarm decisions;
- integrity of mission profiles, alarm policies, telemetry recordings, and event logs;
- availability of the simulator, link emulator, and ground station;
- reproducibility of configuration resolution, fingerprinting, impairment, scheduling, and
  alarm lifecycle evaluation;
- source-code, package-resource, and CI supply-chain integrity.

## Trust boundaries

```text
mission profile -> link resolver
                       |
simulator -> UDP -> link emulator -> UDP -> ground station
                       |                    |       |
                       v                    v       v
                link-event JSONL     telemetry   alarm-event JSONL
                                                 ^
alarm policy -> policy resolver -----------------|
```

Both UDP boundaries are untrusted. External profiles, alarm policies, telemetry recordings,
and imported event logs are untrusted input. The link emulator and alarm engine are simulation
components, not security gateways.

## Current controls

- strict TOML parsing with unknown-key and schema-version rejection;
- package-resource allowlists for built-in profiles and alarm policies;
- no remote downloads, interpolation, executable hooks, or credentials in configuration files;
- pre-socket and pre-log validation of references and effective values;
- canonical effective encodings and deterministic SHA-256 fingerprints;
- exact packet-length, magic, version, flags, mode, and CRC validation;
- bounded fixed-width decoding and bounded impairment values;
- deterministic SplitMix64 decisions and monotonic scheduling;
- session-scoped alarm state, stable identities, hysteresis, and deterministic transition order;
- exact alarm-event key, type, finite-value, ordering, session, metadata, and summary validation;
- legacy schema-version-1 link-event reading;
- no raw datagram payloads in link-event or alarm-event logs;
- deterministic bounded malformed-input corpora for every public parser family;
- read-only default GitHub Actions permissions and pinned Action revisions;
- CI tests, strict typing, coverage, compiler warnings, sanitizers, package checks, and installed
  demos on Linux and macOS.

## Known limitations

- UDP traffic is unauthenticated and unencrypted;
- CRC-32 is not a cryptographic integrity mechanism;
- configuration and policy fingerprints are not signatures, MACs, or provenance proofs;
- plaintext profiles, policies, recordings, and logs can be modified by anyone with file access;
- senders are not authorized or rate-limited;
- replay protection is not implemented;
- event metadata reveals timing, sequence numbers, session identifiers, configuration or policy
  identity, thresholds, observed values, and operational messages;
- external references may reveal local paths;
- operator-provided names and identifiers may contain sensitive information;
- denial-of-service resilience is not a project goal;
- forced termination can leave partial logs.

## Abuse cases

### Malicious or malformed profile or policy

An attacker can provide invalid TOML, unsupported versions, extreme values, ambiguous
references, or unexpected keys. OrbitOps rejects these before creating associated logs or
opening sockets.

A valid profile can still request disruptive but bounded link behavior. A valid alarm policy
can intentionally raise alarms early, late, or not at all within its supported controls.
Configuration expresses simulation behavior; it is not authorization or safety policy.

### Malicious imported log

JSONL can contain wrong top-level types, unknown keys, non-finite numbers, mixed sessions,
invalid ordering, false summaries, or oversized numeric values. Public loaders validate exact
schemas and bounded scalar conversions. Consumers must not trust a file because of its
extension.

### Misleading run evidence

A user can edit a policy or log and recompute a matching fingerprint. Fingerprints identify
effective-behavior equivalence but do not prove who created a run or whether a log is original.

### Metadata disclosure

A local reference, session identifier, alarm message, threshold, or observed value can reveal
usernames, directories, project names, operational conventions, or simulated state. Do not
include secrets or sensitive customer or mission identifiers.

### Datagram injection

An untrusted process can send malformed or fabricated UDP datagrams. Protocol checks protect
parser correctness but do not authenticate the sender.

### Resource exhaustion

A sender can generate high packet rates or long-running sessions. OrbitOps bounds individual
datagrams and configuration values but does not enforce global quotas, rate limits, or
retention.

### Unsafe network exposure

Binding beyond loopback expands the trust boundary without adding encryption, authorization,
or sender identity.

## Safe deployment boundary

Use loopback addresses or a trusted isolated development network. Do not transmit secrets,
personal data, proprietary flight telemetry, or safety-critical commands. Do not expose either
UDP listener directly to the public internet.

Review external profile and policy files before use. Store configurations and logs with
appropriate operating-system permissions, use non-sensitive identifiers, and define retention.

## Future security work

- authenticated command and telemetry envelopes;
- optional transport encryption;
- sender allowlists and rate limiting;
- replay-window enforcement;
- continuous coverage-guided fuzzing outside the normal pull-request CI budget;
- signed run manifests or attestations where provenance is required;
- signed release artifacts and build provenance.

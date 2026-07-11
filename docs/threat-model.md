# Threat model

## Purpose

OrbitOps is a local telemetry simulator, not flight software or a secure communications product. This document makes current trust assumptions explicit so the project is not deployed beyond its intended boundary.

## Assets

- integrity of decoded telemetry;
- integrity of recorded sessions;
- availability of the local ground-station process;
- correctness of protocol and alarm behavior;
- source-code and CI supply-chain integrity.

## Trust boundaries

```text
On-board simulator -> UDP network -> ground station -> JSONL session file
                         ^ untrusted boundary
```

Any UDP datagram must be treated as untrusted input. Session files must also be treated as untrusted when obtained from another source.

## Current controls

- exact packet-length validation;
- protocol magic and version checks;
- reserved-flags validation;
- CRC-32 corruption detection;
- bounded fixed-width decoding;
- rejection of invalid spacecraft modes;
- versioned JSONL records;
- read-only default GitHub Actions permissions;
- pinned GitHub Actions revisions;
- CI tests, type checks, compiler warnings, and sanitizers.

## Known limitations

- UDP traffic is not authenticated or encrypted;
- CRC-32 detects accidental corruption but is not a cryptographic integrity mechanism;
- senders are not authorized or rate-limited;
- the receiver has no application-level replay protection;
- session files are plaintext;
- the simulator uses host wall-clock time;
- denial-of-service resilience is not a goal of the MVP.

## Safe deployment boundary

Use the default loopback address or a trusted isolated development network. Do not transmit secrets, personal data, proprietary telemetry, or safety-critical commands. Do not expose the listener directly to the public internet.

## Future security work

- authenticated command and telemetry envelopes;
- optional transport encryption;
- sender allowlists and rate limiting;
- replay-window enforcement;
- fuzzing of packet and recording parsers;
- signed release artifacts and provenance.

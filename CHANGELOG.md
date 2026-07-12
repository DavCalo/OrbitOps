# Changelog

All notable changes to OrbitOps are documented here. The project follows Semantic Versioning for published releases.

## [Unreleased]

No unreleased changes yet.

## [0.2.0] - 2026-07-12

### Added

- deterministic link-impairment engine with explicit SplitMix64 semantics;
- seeded packet loss, latency, jitter, duplication, one-bit corruption, and bounded reordering;
- UDP link proxy runtime with monotonic scheduling and clean signal-driven shutdown;
- versioned JSONL link events and independently verifiable run statistics;
- public `orbitops link` command with complete pre-socket argument validation;
- `make link-demo` public-CLI scenario spanning the C++ simulator, link emulator, and Python decoder;
- architecture decision record, link-event schema, operating procedures, and security guidance;
- golden decision vectors and unit, runtime, observability, CLI, and end-to-end tests.

### Changed

- expanded OrbitOps from a direct simulator-to-ground-station path into a three-stage telemetry platform;
- updated release, architecture, operations, threat-model, and product documentation;
- updated both Python and C++ version reporting to `0.2.0`.

### Security

- link event logs contain metadata but do not persist raw datagram payloads;
- invalid rates, ports, seeds, timings, and reorder windows are rejected before sockets open;
- documentation now treats both UDP boundaries and imported JSONL logs as untrusted inputs.

## [0.1.0] - 2026-07-12

### Added

- C++17 on-board telemetry simulator;
- fixed-width, CRC-protected telemetry packet and documented golden vector;
- Python UDP ground station with installable `orbitops` command;
- deterministic nominal, thermal, and power scenarios;
- sequence-gap detection, alarms, versioned recording, and replay;
- cross-language protocol compatibility tests;
- Linux and macOS CI coverage;
- Python linting, formatting, strict typing, coverage, and package smoke tests;
- C++ warning-as-error and sanitizer builds;
- security, contribution, support, issue, and pull-request policies;
- architecture, protocol, threat-model, operations, and release documentation.

# Changelog

All notable changes to OrbitOps are documented here. The project follows Semantic Versioning for published releases.

## [Unreleased]

### Added

- explicit session-correlation semantics that preserve source-local clocks, order, and identity
  boundaries;
- immutable normalized telemetry, alarm, and link evidence models with deterministic diagnostics;
- strict non-realtime telemetry loading and independently derived source summaries;
- `orbitops session inspect` with deterministic text and `orbitops.session_report/v1` JSON;
- optional evidence inputs, bounded packet-sequence and alarm filters, explicit timeline limits,
  and atomic `--output` writes;
- installed-wheel session-inspection checks on Linux and macOS;
- deterministic `make session-demo` orchestration across the C++ simulator, link emulator, ground
  station, all three evidence files, installed inspector, and a repository-hosted visual generated
  from validated real output.

### Compatibility

- telemetry recording version `1`, alarm-event version `1`, and link-event versions `1` and `2`
  remain readable through their existing validators;
- telemetry/alarm exact correlation still requires one unique decoded packet-sequence match;
- link `packet_index` remains a separate namespace from telemetry `packet_sequence`;
- filters affect rendered timeline entries only and never rewrite unfiltered source counters;
- the JSON report contract begins at `orbitops.session_report/v1`;
- CLI exit codes distinguish complete, incomplete, usage, incompatible, malformed, and I/O
  outcomes.

## [0.4.0] - 2026-07-13

### Added

- strict versioned alarm-policy TOML with immutable models and stable effective-policy fingerprints;
- bundled `standard`, `conservative`, `thermal-demo`, and `power-demo` alarm policies;
- package-resource and external-file alarm-policy resolution with explicit ambiguity failures;
- `orbitops alarm-policy list`, `show`, and `validate` commands;
- `orbitops listen --alarm-policy` with a backward-compatible default policy;
- session-scoped alarm lifecycle transitions for raised, updated, and cleared states;
- deterministic hysteresis, stable alarm identities, and defined multi-alarm ordering;
- canonical alarm-event JSONL with policy metadata, packet sequences, lifecycle details, and verified summaries;
- `orbitops listen --alarm-log` while keeping telemetry recordings as a separate format;
- `make alarm-demo`, an installed-CLI thermal scenario validated on Linux and macOS;
- deterministic malformed-input corpora and bounded parser mutation helpers for every public parser family;
- architecture, operations, threat-model, schema, parser-hardening, ADR, and release documentation.

### Changed

- alarm output is emitted only on lifecycle transitions instead of repeating unchanged active conditions;
- temperature escalation and de-escalation preserve one logical identity through `updated` events;
- the telemetry replay parser now rejects unknown keys, implicit scalar coercion, non-finite values, negative timestamps, and oversized numeric conversions;
- the complete quality gate now includes the installed alarm demo and alarm-event package smoke test;
- updated both Python and C++ version reporting to `0.4.0`.

### Compatibility

- the binary telemetry protocol remains version `1`;
- mission-profile and alarm-policy schemas remain version `1`;
- link-event emission remains schema version `2`, with schema-version-1 reading preserved;
- alarm-event schema begins at version `1`;
- telemetry recordings, link events, and alarm events remain separate contracts;
- the `standard` alarm policy preserves the effective v0.3 thresholds and zero hysteresis.

### Security

- alarm policies and all imported JSONL/TOML files are treated as untrusted input;
- alarm logs contain decoded operational metadata, never raw telemetry packet bytes;
- exact key sets, finite values, ordering, session identity, and summary counters are validated;
- policy references and operator-selected identifiers are documented as potentially sensitive metadata;
- fingerprints are explicitly reproducibility evidence, not signatures, MACs, provenance proofs, or authorization controls;
- parser defects are minimized into deterministic offline regression fixtures before correction.

## [0.3.0] - 2026-07-12

### Added

- strict versioned TOML mission profiles backed by the Python standard library;
- immutable profile models, canonical effective configurations, and stable SHA-256 fingerprints;
- bundled `nominal`, `intermittent-loss`, `high-latency`, and `degraded-link` profiles;
- package-resource and external-file profile resolution with explicit ambiguity failures;
- `orbitops profile list`, `show`, and `validate` commands;
- `orbitops link --profile` with defaults/profile/explicit-CLI precedence;
- link-event schema version 2 with a leading profile-aware `run_metadata` record;
- `make profile-demo` end-to-end validation through the installed CLI on Linux and macOS;
- profile schema, catalog, observability, operations, architecture, and security documentation.

### Changed

- preserved schema-version-1 link-event loading while emitting schema version 2 for new runs;
- kept packet-event attributes and `run_summary` counter semantics unchanged;
- moved effective-link fingerprint ownership into the link package while retaining profile API exports;
- updated both Python and C++ version reporting to `0.3.0`.

### Security

- malformed, unsupported, missing, and ambiguous profiles fail before sockets or log files open;
- profile documents are data-only and cannot contain executable hooks or credentials;
- event metadata contains fingerprints rather than raw effective-configuration documents;
- external profile references and session identifiers are documented as potentially sensitive metadata;
- configuration fingerprints are explicitly documented as reproducibility evidence, not authenticity.

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

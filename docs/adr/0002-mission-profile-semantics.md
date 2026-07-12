# ADR 0002: Versioned mission-profile semantics

- **Status:** Accepted
- **Date:** 2026-07-12
- **Target:** OrbitOps v0.3.0
- **Parent epic:** Versioned mission profiles

## Context

OrbitOps v0.2.0 exposes deterministic link impairments through explicit command-line
options. The configuration is reproducible, but operators must repeat every option and
there is no portable identity for the effective configuration used by a run.

Mission profiles will make link scenarios reusable and auditable. The first increment
intentionally excludes file discovery, built-in package resources, command-line
integration, event metadata, and precedence rules. It defines only the pure profile
contract: TOML parsing, validation, normalization, canonical representation, and
fingerprinting.

## Decision

### Document format

Mission profiles use TOML and are parsed with Python's standard-library `tomllib`.
No runtime dependency is added.

A schema-version 1 document has this shape:

```toml
schema_version = 1
name = "degraded-link"
description = "Optional operator-facing description."

[link]
seed = 42
loss_rate = 0.05
duplicate_rate = 0.02
corrupt_rate = 0.01
latency_ms = 120
jitter_ms = 30
reorder_window = 3
```

`schema_version`, `name`, and the `[link]` table are required. `description` is
optional. Every link field is optional and inherits the existing `LinkConfig` default.
An empty `[link]` table therefore represents exact pass-through behavior.

### Strict schema

Unknown top-level keys and unknown `[link]` keys are rejected. Silently ignoring a
misspelled or unsupported option could produce a run whose behavior differs from the
operator's intent.

Unsupported schema versions are rejected before any runtime or socket integration.
Malformed TOML is reported separately from a structurally valid document that violates
the OrbitOps schema.

### Profile identity

`name` is a stable lowercase slug of one to 64 characters. It may contain ASCII
letters, digits, and internal hyphens, but may not begin or end with a hyphen.

`description` is operator-facing metadata. When present, it must be non-empty, at most
500 characters, and contain no NUL character.

Profile metadata does not change link behavior and is not part of the effective
configuration fingerprint.

### Link validation and normalization

Profile values reuse the existing `LinkConfig` contract:

- `seed` is an unsigned 64-bit integer;
- rates are finite values in the inclusive interval `0.0` through `1.0`;
- latency and jitter are non-negative integer milliseconds;
- the reorder window is an integer from zero through 65,535.

TOML integers used for rates are normalized to Python `float` values before creating
`LinkConfig`. This ensures that semantically equivalent documents such as `0`, `0.0`,
and differently ordered tables resolve to the same effective model.

### Canonical effective configuration

The canonical representation is compact JSON with sorted keys. It contains only the
effective `LinkConfig` and an independent canonical-schema version.

Probability values use Python's exact hexadecimal floating-point representation. This
avoids dependence on source TOML formatting, locale, or a human-oriented decimal
rendering policy.

The canonical representation does not contain:

- profile name or description;
- source path;
- comments or TOML key order;
- runtime-generated session identifiers;
- socket endpoints or timestamps.

### Fingerprint

The effective-configuration fingerprint is:

```text
sha256:<lowercase hexadecimal digest>
```

The digest is SHA-256 over the ASCII bytes of the canonical JSON representation.
Equivalent effective configurations must produce the same fingerprint, regardless of
profile metadata or source-document formatting.

The fingerprint identifies configuration, not trust. It is not a signature and does
not authenticate the profile or the operator.

### Deferred precedence

This increment does not merge profiles with command-line arguments. A later increment
will implement the previously agreed precedence:

1. OrbitOps defaults;
2. selected mission profile;
3. explicitly supplied command-line options.

Omitted command-line options must not overwrite profile values.

## Consequences

### Positive

- Profiles are dependency-free, immutable, and testable without sockets or clocks.
- Misspelled configuration cannot be silently accepted.
- Existing `LinkConfig` semantics remain the single validation authority.
- Golden canonical text and digest vectors detect accidental compatibility changes.
- Equivalent profiles can be compared without depending on names or file paths.
- Later event logs can record a compact, deterministic configuration identity.

### Trade-offs

- Schema version 1 intentionally supports only the existing link-emulator fields.
- Strict unknown-key rejection requires an explicit schema update for every new field.
- Hexadecimal float strings are exact but less readable than decimal values.
- SHA-256 detects configuration equality; it does not make a profile safe or trusted.
- Profile discovery, built-in catalogs, CLI overrides, and package resources remain for
  subsequent increments.

## Compatibility policy

Changing any of the following is a compatibility change:

- schema-version 1 keys or required-field rules;
- profile-name validation;
- link-value normalization;
- canonical JSON structure or field names;
- hexadecimal float encoding;
- fingerprint prefix or hashing algorithm;
- the committed golden canonical representation or digest.

Such a change requires a new ADR or an explicit revision of this ADR, updated golden
vectors, and a changelog entry.

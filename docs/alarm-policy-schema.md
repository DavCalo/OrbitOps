# OrbitOps alarm policy schema

OrbitOps alarm policies are strict UTF-8 TOML documents. Schema version `1`
defines deterministic ground-station alarm behavior; it does not define
flight-certified limits or spacecraft safety requirements.

## Complete document

```toml
schema_version = 1
name = "standard"
description = "Backward-compatible OrbitOps v0.3 alarm thresholds."

[temperature]
warning_c = 50.0
critical_c = 60.0
hysteresis_c = 0.0

[battery]
critical_v = 7.0
hysteresis_v = 0.0

[mode]
alarm_on_safe = true

[sequence]
detect_gaps = true
```

All four tables and every table field are required. `description` is optional.
Unknown top-level keys, tables, and table fields are rejected.

## Validation contract

- `schema_version` must be the integer `1`;
- `name` is a lowercase slug of at most 64 characters;
- numeric values must be finite and booleans are not accepted as numbers;
- `temperature.warning_c` is lower than `temperature.critical_c`;
- hysteresis values are non-negative;
- the critical-temperature clear boundary may not fall below the warning threshold;
- `battery.critical_v` is positive;
- mode and sequence switches are strict booleans.

The temperature clear boundaries are derived by subtracting `hysteresis_c` from
the corresponding high-temperature activation threshold. The low-battery clear
boundary is derived by adding `hysteresis_v` to `critical_v`. Lifecycle behavior
is implemented separately by the alarm engine.

## Canonical fingerprint

`canonical_effective_alarm_policy()` serializes behavior-affecting fields as
compact, sorted JSON. Floating-point values use exact hexadecimal notation.
Policy name and description are excluded, so equivalent effective policies have
the same SHA-256 fingerprint even when their source formatting or identity differs.

A fingerprint is reproducibility evidence. It is not a digital signature,
authenticity guarantee, or proof that a policy is operationally safe.

## Security and scope

Policy files contain data only: no commands, imports, credentials, remote URLs,
or executable expressions. Imported policies are untrusted input and must be
validated before sockets are bound or logs are created.

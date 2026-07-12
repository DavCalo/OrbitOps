# ADR 0003: Deterministic alarm lifecycle semantics

## Status

Accepted for OrbitOps v0.4.0.

## Context

OrbitOps v0.3 evaluates thresholds independently for every telemetry packet. An active
condition is therefore printed repeatedly, and recovery is not represented explicitly.
The v0.4.0 alarm-policy model also introduces hysteresis, which requires session-scoped
state and precise boundary semantics.

## Decision

`AlarmEngine` owns all lifecycle state for one listener session and emits immutable
`AlarmTransition` values. The supported transition types are:

- `raised`: an inactive alarm becomes active;
- `updated`: one logical alarm changes material state, currently temperature severity;
- `cleared`: an active alarm recovers beyond its hysteresis boundary.

The engine emits no transition while an alarm remains unchanged. It can be reset
explicitly before reuse in a new session.

### Stable identities

Temperature is one logical alarm identity. Its presentation changes between:

- `ELEVATED_TEMPERATURE` / warning;
- `HIGH_TEMPERATURE` / critical.

Warning-to-critical escalation and critical-to-warning de-escalation each emit one
`updated` transition. This preserves a stable lifecycle identity while retaining the
v0.3 terminal codes.

Battery and SAFE mode each have one stateful identity. Sequence gaps are occurrence
events: each detected gap emits `raised`, but the gap is never stored as active and
therefore does not emit `cleared`.

### Hysteresis boundaries

For high-temperature alarms, recovery must move strictly below the configured clear
boundary:

- warning clear boundary = `warning_c - hysteresis_c`;
- critical clear boundary = `critical_c - hysteresis_c`.

For low battery, recovery must move strictly above:

- `critical_v + hysteresis_v`.

Equality remains active. This prevents boundary chatter and makes all supported
platforms evaluate the same packet stream identically.

### Deterministic ordering

When one packet causes multiple transitions, the order is always:

1. sequence integrity;
2. temperature;
3. battery;
4. spacecraft mode.

### Compatibility

The default policy keeps the v0.3 thresholds and zero hysteresis. Raised transitions
retain the previous terminal line shape. Updated and cleared transitions add an
explicit lifecycle label. Telemetry decoding and packet formats are unchanged.

## Consequences

- repeated packets no longer print duplicate active-alarm messages;
- consumers can distinguish activation, escalation, recovery, and occurrence events;
- one `AlarmEngine` instance must not be shared across independent listener sessions;
- future alarm-event logging can serialize transition metadata without re-evaluating
  telemetry;
- configurable policy loading, CLI selection, and JSONL alarm logs remain separate
  increments.

"""Deterministic alarm lifecycle evaluation for OrbitOps telemetry."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TypeAlias

from .alarm_policies import (
    ALARM_POLICY_SCHEMA_VERSION,
    AlarmPolicy,
    BatteryAlarmPolicy,
    ModeAlarmPolicy,
    SequenceAlarmPolicy,
    TemperatureAlarmPolicy,
)
from .protocol import Mode, TelemetryPacket

AlarmObservedValue: TypeAlias = float | int | str | None
AlarmThreshold: TypeAlias = float | int | None


class AlarmSeverity(enum.StrEnum):
    """Severity assigned to an alarm presentation."""

    WARNING = "warning"
    CRITICAL = "critical"


class AlarmTransitionType(enum.StrEnum):
    """Lifecycle change emitted by the alarm engine."""

    RAISED = "raised"
    UPDATED = "updated"
    CLEARED = "cleared"


@dataclass(frozen=True, slots=True)
class AlarmIdentity:
    """Stable identity for one logical alarm across lifecycle transitions."""

    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("alarm identity name must not be empty")


@dataclass(frozen=True, slots=True)
class Alarm:
    """Backward-compatible alarm presentation fields."""

    severity: AlarmSeverity
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class AlarmTransition(Alarm):
    """Immutable state transition emitted for one logical alarm."""

    identity: AlarmIdentity
    transition: AlarmTransitionType
    observed_value: AlarmObservedValue = None
    threshold: AlarmThreshold = None


DEFAULT_ALARM_POLICY = AlarmPolicy(
    schema_version=ALARM_POLICY_SCHEMA_VERSION,
    name="standard",
    description="Backward-compatible OrbitOps v0.3 alarm thresholds.",
    temperature=TemperatureAlarmPolicy(
        warning_c=50.0,
        critical_c=60.0,
        hysteresis_c=0.0,
    ),
    battery=BatteryAlarmPolicy(
        critical_v=7.0,
        hysteresis_v=0.0,
    ),
    mode=ModeAlarmPolicy(alarm_on_safe=True),
    sequence=SequenceAlarmPolicy(detect_gaps=True),
)

_TEMPERATURE = AlarmIdentity("temperature")
_BATTERY = AlarmIdentity("battery")
_SAFE_MODE = AlarmIdentity("safe-mode")
_SEQUENCE_GAP = AlarmIdentity("sequence-gap")


class AlarmEngine:
    """Evaluate an ordered packet stream with session-scoped alarm state."""

    __slots__ = (
        "_battery_active",
        "_last_sequence",
        "_policy",
        "_safe_mode_active",
        "_temperature_severity",
    )

    def __init__(self, policy: AlarmPolicy = DEFAULT_ALARM_POLICY) -> None:
        if not isinstance(policy, AlarmPolicy):
            raise TypeError("policy must be an AlarmPolicy instance")
        self._policy = policy
        self.reset()

    @property
    def policy(self) -> AlarmPolicy:
        """Return the immutable policy used by this engine instance."""

        return self._policy

    @property
    def active_alarm_identities(self) -> tuple[AlarmIdentity, ...]:
        """Return active stateful alarms in deterministic presentation order."""

        active: list[AlarmIdentity] = []
        if self._temperature_severity is not None:
            active.append(_TEMPERATURE)
        if self._battery_active:
            active.append(_BATTERY)
        if self._safe_mode_active:
            active.append(_SAFE_MODE)
        return tuple(active)

    def reset(self) -> None:
        """Reset sequence tracking and all active alarms for a new session."""

        self._last_sequence: int | None = None
        self._temperature_severity: AlarmSeverity | None = None
        self._battery_active = False
        self._safe_mode_active = False

    def evaluate(self, packet: TelemetryPacket) -> list[AlarmTransition]:
        """Evaluate one packet and emit only lifecycle changes."""

        transitions: list[AlarmTransition] = []
        sequence_transition = self._evaluate_sequence(packet)
        if sequence_transition is not None:
            transitions.append(sequence_transition)

        temperature_transition = self._evaluate_temperature(packet)
        if temperature_transition is not None:
            transitions.append(temperature_transition)

        battery_transition = self._evaluate_battery(packet)
        if battery_transition is not None:
            transitions.append(battery_transition)

        mode_transition = self._evaluate_mode(packet)
        if mode_transition is not None:
            transitions.append(mode_transition)

        return transitions

    def _evaluate_sequence(self, packet: TelemetryPacket) -> AlarmTransition | None:
        expected: int | None = None
        if self._last_sequence is not None:
            expected = (self._last_sequence + 1) & 0xFFFFFFFF
        self._last_sequence = packet.sequence

        if not self._policy.sequence.detect_gaps or expected is None or packet.sequence == expected:
            return None

        # Sequence gaps are occurrence events: they are emitted but never stored as active state.
        return AlarmTransition(
            severity=AlarmSeverity.WARNING,
            code="SEQUENCE_GAP",
            message=f"expected sequence {expected}, received {packet.sequence}",
            identity=_SEQUENCE_GAP,
            transition=AlarmTransitionType.RAISED,
            observed_value=packet.sequence,
            threshold=expected,
        )

    def _evaluate_temperature(self, packet: TelemetryPacket) -> AlarmTransition | None:
        previous = self._temperature_severity
        current = self._next_temperature_severity(packet.temperature_c)
        self._temperature_severity = current

        if current is previous:
            return None
        if previous is None and current is not None:
            return self._temperature_transition(
                AlarmTransitionType.RAISED,
                current,
                packet.temperature_c,
                self._temperature_entry_threshold(current),
            )
        if previous is not None and current is None:
            return self._temperature_transition(
                AlarmTransitionType.CLEARED,
                previous,
                packet.temperature_c,
                self._policy.temperature.warning_c - self._policy.temperature.hysteresis_c,
            )
        if previous is not None and current is not None:
            # Temperature keeps one stable identity while severity and presentation code change.
            threshold = (
                self._policy.temperature.critical_c
                if current is AlarmSeverity.CRITICAL
                else self._policy.temperature.critical_c - self._policy.temperature.hysteresis_c
            )
            return self._temperature_transition(
                AlarmTransitionType.UPDATED,
                current,
                packet.temperature_c,
                threshold,
            )
        raise AssertionError("unreachable temperature lifecycle state")

    def _next_temperature_severity(self, temperature_c: float) -> AlarmSeverity | None:
        policy = self._policy.temperature
        warning_clear_c = policy.warning_c - policy.hysteresis_c
        critical_clear_c = policy.critical_c - policy.hysteresis_c

        if self._temperature_severity is None:
            if temperature_c >= policy.critical_c:
                return AlarmSeverity.CRITICAL
            if temperature_c >= policy.warning_c:
                return AlarmSeverity.WARNING
            return None

        if self._temperature_severity is AlarmSeverity.WARNING:
            if temperature_c >= policy.critical_c:
                return AlarmSeverity.CRITICAL
            # Equality remains active; recovery must move beyond the hysteresis boundary.
            if temperature_c < warning_clear_c:
                return None
            return AlarmSeverity.WARNING

        if temperature_c >= critical_clear_c:
            return AlarmSeverity.CRITICAL
        if temperature_c >= warning_clear_c:
            return AlarmSeverity.WARNING
        return None

    def _temperature_entry_threshold(self, severity: AlarmSeverity) -> float:
        if severity is AlarmSeverity.CRITICAL:
            return self._policy.temperature.critical_c
        return self._policy.temperature.warning_c

    @staticmethod
    def _temperature_code(severity: AlarmSeverity) -> str:
        if severity is AlarmSeverity.CRITICAL:
            return "HIGH_TEMPERATURE"
        return "ELEVATED_TEMPERATURE"

    def _temperature_transition(
        self,
        transition: AlarmTransitionType,
        severity: AlarmSeverity,
        observed: float,
        threshold: float,
    ) -> AlarmTransition:
        message = (
            f"temperature recovered to {observed:.2f} °C"
            if transition is AlarmTransitionType.CLEARED
            else f"temperature is {observed:.2f} °C"
        )
        return AlarmTransition(
            severity=severity,
            code=self._temperature_code(severity),
            message=message,
            identity=_TEMPERATURE,
            transition=transition,
            observed_value=observed,
            threshold=threshold,
        )

    def _evaluate_battery(self, packet: TelemetryPacket) -> AlarmTransition | None:
        policy = self._policy.battery
        previous = self._battery_active
        current = (
            packet.battery_v <= policy.critical_v
            if not previous
            else packet.battery_v <= policy.critical_v + policy.hysteresis_v
        )
        self._battery_active = current

        if current is previous:
            return None

        transition = AlarmTransitionType.RAISED if current else AlarmTransitionType.CLEARED
        message = (
            f"battery voltage is {packet.battery_v:.3f} V"
            if current
            else f"battery voltage recovered to {packet.battery_v:.3f} V"
        )
        return AlarmTransition(
            severity=AlarmSeverity.CRITICAL,
            code="LOW_BATTERY",
            message=message,
            identity=_BATTERY,
            transition=transition,
            observed_value=packet.battery_v,
            threshold=(policy.critical_v if current else policy.critical_v + policy.hysteresis_v),
        )

    def _evaluate_mode(self, packet: TelemetryPacket) -> AlarmTransition | None:
        current = self._policy.mode.alarm_on_safe and packet.mode is Mode.SAFE
        previous = self._safe_mode_active
        self._safe_mode_active = current

        if current is previous:
            return None

        return AlarmTransition(
            severity=AlarmSeverity.WARNING,
            code="SAFE_MODE",
            message=("spacecraft reports SAFE mode" if current else "spacecraft exited SAFE mode"),
            identity=_SAFE_MODE,
            transition=(AlarmTransitionType.RAISED if current else AlarmTransitionType.CLEARED),
            observed_value=packet.mode.name,
        )


def format_alarm_transition(alarm: AlarmTransition) -> str:
    """Render a transition while preserving the v0.3 raised-alarm format."""

    if alarm.transition is AlarmTransitionType.RAISED:
        marker = "!" if alarm.severity is AlarmSeverity.WARNING else "!!"
        return f"  {marker} {alarm.severity.upper():8} {alarm.code}: {alarm.message}"

    marker = "~" if alarm.transition is AlarmTransitionType.UPDATED else "OK"
    return (
        f"  {marker} {alarm.severity.upper():8} {alarm.code} "
        f"[{alarm.transition.upper()}]: {alarm.message}"
    )

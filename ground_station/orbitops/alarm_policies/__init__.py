"""Versioned alarm-policy primitives for OrbitOps."""

from .errors import (
    AlarmPolicyAmbiguousReferenceError,
    AlarmPolicyError,
    AlarmPolicyLoadError,
    AlarmPolicyNotFoundError,
    AlarmPolicyParseError,
    AlarmPolicyValidationError,
)
from .fingerprint import (
    ALARM_POLICY_FINGERPRINT_SCHEMA_VERSION,
    alarm_policy_fingerprint,
    canonical_effective_alarm_policy,
)
from .model import (
    ALARM_POLICY_SCHEMA_VERSION,
    AlarmPolicy,
    BatteryAlarmPolicy,
    ModeAlarmPolicy,
    SequenceAlarmPolicy,
    TemperatureAlarmPolicy,
)
from .parser import parse_alarm_policy

__all__ = [
    "ALARM_POLICY_FINGERPRINT_SCHEMA_VERSION",
    "ALARM_POLICY_SCHEMA_VERSION",
    "AlarmPolicy",
    "AlarmPolicyAmbiguousReferenceError",
    "AlarmPolicyError",
    "AlarmPolicyLoadError",
    "AlarmPolicyNotFoundError",
    "AlarmPolicyParseError",
    "AlarmPolicyValidationError",
    "BatteryAlarmPolicy",
    "ModeAlarmPolicy",
    "SequenceAlarmPolicy",
    "TemperatureAlarmPolicy",
    "alarm_policy_fingerprint",
    "canonical_effective_alarm_policy",
    "parse_alarm_policy",
]

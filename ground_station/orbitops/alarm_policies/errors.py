"""Alarm-policy error hierarchy."""


class AlarmPolicyError(ValueError):
    """Base class for alarm-policy parsing, validation, and loading failures."""


class AlarmPolicyParseError(AlarmPolicyError):
    """Raised when an alarm-policy TOML document cannot be parsed."""


class AlarmPolicyValidationError(AlarmPolicyError):
    """Raised when a parsed alarm policy violates the OrbitOps schema."""


class AlarmPolicyLoadError(AlarmPolicyError):
    """Raised when an alarm policy cannot be loaded from storage."""


class AlarmPolicyNotFoundError(AlarmPolicyLoadError):
    """Raised when a requested built-in or external alarm policy does not exist."""


class AlarmPolicyAmbiguousReferenceError(AlarmPolicyError):
    """Raised when a short reference matches both a built-in policy and a file."""

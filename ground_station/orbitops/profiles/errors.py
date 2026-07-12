"""Mission-profile error hierarchy."""


class MissionProfileError(ValueError):
    """Base class for mission-profile parsing and validation failures."""


class MissionProfileParseError(MissionProfileError):
    """Raised when a TOML document cannot be parsed."""


class MissionProfileValidationError(MissionProfileError):
    """Raised when a parsed profile violates the OrbitOps profile schema."""


class MissionProfileLoadError(MissionProfileError):
    """Raised when a mission profile cannot be loaded from storage."""


class MissionProfileNotFoundError(MissionProfileLoadError):
    """Raised when a requested built-in or external profile does not exist."""


class MissionProfileAmbiguousReferenceError(MissionProfileError):
    """Raised when a short reference matches both a built-in profile and a file."""

"""Mission-profile error hierarchy."""


class MissionProfileError(ValueError):
    """Base class for mission-profile parsing and validation failures."""


class MissionProfileParseError(MissionProfileError):
    """Raised when a TOML document cannot be parsed."""


class MissionProfileValidationError(MissionProfileError):
    """Raised when a parsed profile violates the OrbitOps profile schema."""

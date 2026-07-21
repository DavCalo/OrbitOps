"""Error hierarchy for unified session inspection."""

from __future__ import annotations

from .correlation import EvidenceLane


class SessionInspectionError(ValueError):
    """Base class for errors raised while building or consuming a session model."""

    def __init__(
        self,
        message: str,
        *,
        lane: EvidenceLane | None = None,
        source_name: str | None = None,
    ) -> None:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string")
        if lane is not None and not isinstance(lane, EvidenceLane):
            raise TypeError("lane must be an EvidenceLane or None")
        if source_name is not None:
            if not isinstance(source_name, str) or not source_name.strip():
                raise ValueError("source_name must be non-empty when provided")
            if "\x00" in source_name:
                raise ValueError("source_name must not contain NUL characters")
        self.lane = lane
        self.source_name = source_name
        super().__init__(message)


class MalformedEvidenceError(SessionInspectionError):
    """A selected source cannot be decoded through its strict contract."""


class IncompatibleEvidenceError(SessionInspectionError):
    """Selected evidence is valid in isolation but violates a proven compatibility rule."""


class IncompleteEvidenceError(SessionInspectionError):
    """A caller required complete evidence but at least one source is incomplete."""

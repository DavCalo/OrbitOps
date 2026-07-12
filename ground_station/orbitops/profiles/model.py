"""Immutable mission-profile model."""

from __future__ import annotations

import re
from dataclasses import dataclass

from orbitops.link.config import LinkConfig

MISSION_PROFILE_SCHEMA_VERSION = 1
_MAX_PROFILE_NAME_LENGTH = 64
_MAX_DESCRIPTION_LENGTH = 500
_PROFILE_NAME_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")


@dataclass(frozen=True, slots=True)
class MissionProfile:
    """Validated, immutable mission-profile definition."""

    schema_version: int
    name: str
    description: str | None
    link_config: LinkConfig

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("schema_version must be an integer")
        if self.schema_version != MISSION_PROFILE_SCHEMA_VERSION:
            raise ValueError(
                "unsupported schema_version "
                f"{self.schema_version}; expected {MISSION_PROFILE_SCHEMA_VERSION}"
            )
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if (
            len(self.name) > _MAX_PROFILE_NAME_LENGTH
            or _PROFILE_NAME_PATTERN.fullmatch(self.name) is None
        ):
            raise ValueError(
                "name must be a lowercase slug of 1 to 64 characters using letters, digits, and "
                "hyphens; hyphens may not be leading or trailing"
            )
        if self.description is not None:
            if not isinstance(self.description, str):
                raise TypeError("description must be a string or None")
            if not self.description:
                raise ValueError("description must not be empty when provided")
            if len(self.description) > _MAX_DESCRIPTION_LENGTH:
                raise ValueError(
                    f"description must be at most {_MAX_DESCRIPTION_LENGTH} characters"
                )
            if "\x00" in self.description:
                raise ValueError("description must not contain NUL characters")
        if not isinstance(self.link_config, LinkConfig):
            raise TypeError("link_config must be a LinkConfig instance")

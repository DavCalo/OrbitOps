"""Built-in mission-profile catalog and external-file resolution."""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path

from .errors import (
    MissionProfileAmbiguousReferenceError,
    MissionProfileLoadError,
    MissionProfileNotFoundError,
    MissionProfileValidationError,
)
from .model import MissionProfile
from .parser import parse_mission_profile

_BUILTIN_PACKAGE = "orbitops.profiles.builtin"
_BUILTIN_PROFILE_NAMES = (
    "nominal",
    "intermittent-loss",
    "high-latency",
    "degraded-link",
)
_BUILTIN_PREFIX = "builtin:"
_FILE_PREFIX = "file:"


def list_builtin_profiles() -> tuple[str, ...]:
    """Return the stable built-in profile names in product-display order."""

    return _BUILTIN_PROFILE_NAMES


def _available_builtin_profiles() -> str:
    return ", ".join(_BUILTIN_PROFILE_NAMES)


def load_builtin_profile(name: str) -> MissionProfile:
    """Load and validate one profile bundled with the OrbitOps package."""

    if not isinstance(name, str):
        raise TypeError("name must be a string")
    if not name:
        raise ValueError("name must not be empty")
    if name not in _BUILTIN_PROFILE_NAMES:
        raise MissionProfileNotFoundError(
            f"unknown built-in mission profile {name!r}; available profiles: "
            f"{_available_builtin_profiles()}"
        )

    source = f"{_BUILTIN_PREFIX}{name}"
    try:
        resource = resources.files(_BUILTIN_PACKAGE).joinpath(f"{name}.toml")
        document = resource.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise MissionProfileNotFoundError(
            f"{source}: bundled profile resource is missing from the installed package"
        ) from exc
    except (ModuleNotFoundError, OSError, UnicodeError) as exc:
        raise MissionProfileLoadError(f"{source}: unable to read bundled profile: {exc}") from exc

    profile = parse_mission_profile(document, source=source)
    if profile.name != name:
        raise MissionProfileValidationError(
            f"{source}: profile name {profile.name!r} does not match resource name {name!r}"
        )
    return profile


def _coerce_profile_path(path: str | os.PathLike[str]) -> Path:
    if isinstance(path, str):
        raw_path = path
    elif isinstance(path, os.PathLike):
        raw_path = os.fspath(path)
        if not isinstance(raw_path, str):
            raise TypeError("path must resolve to text, not bytes")
    else:
        raise TypeError("path must be a string or path-like object")
    if not raw_path:
        raise ValueError("path must not be empty")
    return Path(raw_path)


def load_mission_profile_file(path: str | os.PathLike[str]) -> MissionProfile:
    """Load and validate one UTF-8 mission-profile TOML file."""

    profile_path = _coerce_profile_path(path)
    source = f"{_FILE_PREFIX}{profile_path}"
    try:
        if not profile_path.is_file():
            raise MissionProfileNotFoundError(
                f"{source}: mission profile does not exist or is not a regular file"
            )
        document = profile_path.read_text(encoding="utf-8")
    except MissionProfileNotFoundError:
        raise
    except UnicodeError as exc:
        raise MissionProfileLoadError(f"{source}: mission profile is not valid UTF-8") from exc
    except OSError as exc:
        raise MissionProfileLoadError(f"{source}: unable to read mission profile: {exc}") from exc

    return parse_mission_profile(document, source=source)


def resolve_mission_profile(reference: str | os.PathLike[str]) -> MissionProfile:
    """Resolve a built-in name or external file reference.

    String references support explicit ``builtin:<name>`` and ``file:<path>`` forms.
    A bare string may select a built-in profile or an existing file. If it matches
    both, callers must use an explicit form to avoid environment-dependent behavior.
    Path-like objects always select an external file.
    """

    if not isinstance(reference, str):
        return load_mission_profile_file(reference)
    if not reference:
        raise ValueError("reference must not be empty")

    if reference.startswith(_BUILTIN_PREFIX):
        name = reference.removeprefix(_BUILTIN_PREFIX)
        if not name:
            raise ValueError("built-in profile reference must include a name")
        return load_builtin_profile(name)

    if reference.startswith(_FILE_PREFIX):
        path = reference.removeprefix(_FILE_PREFIX)
        if not path:
            raise ValueError("file profile reference must include a path")
        return load_mission_profile_file(path)

    matches_builtin = reference in _BUILTIN_PROFILE_NAMES
    candidate = Path(reference)
    try:
        matches_file = candidate.is_file()
    except OSError as exc:
        raise MissionProfileLoadError(
            f"file:{candidate}: unable to inspect mission-profile path: {exc}"
        ) from exc

    if matches_builtin and matches_file:
        raise MissionProfileAmbiguousReferenceError(
            f"ambiguous mission profile reference {reference!r}; use "
            f"{_BUILTIN_PREFIX}{reference} for the bundled profile or "
            f"{_FILE_PREFIX}{reference} for the external file"
        )
    if matches_builtin:
        return load_builtin_profile(reference)
    if matches_file:
        return load_mission_profile_file(candidate)

    raise MissionProfileNotFoundError(
        f"mission profile reference {reference!r} did not match a built-in profile or file; "
        f"available built-ins: {_available_builtin_profiles()}"
    )

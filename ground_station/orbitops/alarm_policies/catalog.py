"""Built-in alarm-policy catalog and external-file resolution."""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path

from .errors import (
    AlarmPolicyAmbiguousReferenceError,
    AlarmPolicyLoadError,
    AlarmPolicyNotFoundError,
    AlarmPolicyValidationError,
)
from .model import AlarmPolicy
from .parser import parse_alarm_policy

_BUILTIN_PACKAGE = "orbitops.alarm_policies.builtin"
_BUILTIN_POLICY_NAMES = (
    "standard",
    "conservative",
    "thermal-demo",
    "power-demo",
)
_BUILTIN_PREFIX = "builtin:"
_FILE_PREFIX = "file:"


def list_builtin_alarm_policies() -> tuple[str, ...]:
    """Return stable built-in policy names in product-display order."""

    return _BUILTIN_POLICY_NAMES


def _available_builtin_policies() -> str:
    return ", ".join(_BUILTIN_POLICY_NAMES)


def load_builtin_alarm_policy(name: str) -> AlarmPolicy:
    """Load and validate one alarm policy bundled with OrbitOps."""

    if not isinstance(name, str):
        raise TypeError("name must be a string")
    if not name:
        raise ValueError("name must not be empty")
    if name not in _BUILTIN_POLICY_NAMES:
        raise AlarmPolicyNotFoundError(
            f"unknown built-in alarm policy {name!r}; available policies: "
            f"{_available_builtin_policies()}"
        )

    source = f"{_BUILTIN_PREFIX}{name}"
    try:
        resource = resources.files(_BUILTIN_PACKAGE).joinpath(f"{name}.toml")
        document = resource.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AlarmPolicyNotFoundError(
            f"{source}: bundled policy resource is missing from the installed package"
        ) from exc
    except (ModuleNotFoundError, OSError, UnicodeError) as exc:
        raise AlarmPolicyLoadError(f"{source}: unable to read bundled policy: {exc}") from exc

    policy = parse_alarm_policy(document, source=source)
    if policy.name != name:
        raise AlarmPolicyValidationError(
            f"{source}: policy name {policy.name!r} does not match resource name {name!r}"
        )
    return policy


def _coerce_policy_path(path: str | os.PathLike[str]) -> Path:
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


def load_alarm_policy_file(path: str | os.PathLike[str]) -> AlarmPolicy:
    """Load and validate one UTF-8 alarm-policy TOML file."""

    policy_path = _coerce_policy_path(path)
    source = f"{_FILE_PREFIX}{policy_path}"
    try:
        if not policy_path.is_file():
            raise AlarmPolicyNotFoundError(
                f"{source}: alarm policy does not exist or is not a regular file"
            )
        document = policy_path.read_text(encoding="utf-8")
    except AlarmPolicyNotFoundError:
        raise
    except UnicodeError as exc:
        raise AlarmPolicyLoadError(f"{source}: alarm policy is not valid UTF-8") from exc
    except OSError as exc:
        raise AlarmPolicyLoadError(f"{source}: unable to read alarm policy: {exc}") from exc

    return parse_alarm_policy(document, source=source)


def resolve_alarm_policy(reference: str | os.PathLike[str]) -> AlarmPolicy:
    """Resolve a built-in alarm policy or external file reference.

    Strings support explicit ``builtin:<name>`` and ``file:<path>`` forms. A bare
    string may select a built-in policy or an existing file. If it matches both,
    callers must choose an explicit namespace. Path-like objects always select files.
    """

    if not isinstance(reference, str):
        return load_alarm_policy_file(reference)
    if not reference:
        raise ValueError("reference must not be empty")

    if reference.startswith(_BUILTIN_PREFIX):
        name = reference.removeprefix(_BUILTIN_PREFIX)
        if not name:
            raise ValueError("built-in alarm-policy reference must include a name")
        return load_builtin_alarm_policy(name)

    if reference.startswith(_FILE_PREFIX):
        path = reference.removeprefix(_FILE_PREFIX)
        if not path:
            raise ValueError("file alarm-policy reference must include a path")
        return load_alarm_policy_file(path)

    matches_builtin = reference in _BUILTIN_POLICY_NAMES
    candidate = Path(reference)
    try:
        matches_file = candidate.is_file()
    except OSError as exc:
        raise AlarmPolicyLoadError(
            f"file:{candidate}: unable to inspect alarm-policy path: {exc}"
        ) from exc

    if matches_builtin and matches_file:
        raise AlarmPolicyAmbiguousReferenceError(
            f"ambiguous alarm policy reference {reference!r}; use "
            f"{_BUILTIN_PREFIX}{reference} for the bundled policy or "
            f"{_FILE_PREFIX}{reference} for the external file"
        )
    if matches_builtin:
        return load_builtin_alarm_policy(reference)
    if matches_file:
        return load_alarm_policy_file(candidate)

    raise AlarmPolicyNotFoundError(
        f"alarm policy reference {reference!r} did not match a built-in policy or file; "
        f"available built-ins: {_available_builtin_policies()}"
    )

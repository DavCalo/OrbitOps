"""Canonical effective-configuration encoding and fingerprinting."""

from __future__ import annotations

import hashlib
import json

from orbitops.link.config import LinkConfig

EFFECTIVE_CONFIG_SCHEMA_VERSION = 1


def canonical_effective_config(config: LinkConfig) -> str:
    """Return the canonical JSON representation of an effective link configuration.

    Probability values use Python's exact hexadecimal floating-point form so the
    representation does not depend on source TOML formatting or locale.
    """

    if not isinstance(config, LinkConfig):
        raise TypeError("config must be a LinkConfig instance")

    document = {
        "schema_version": EFFECTIVE_CONFIG_SCHEMA_VERSION,
        "link": {
            "seed": config.seed,
            "loss_rate": float(config.loss_rate).hex(),
            "duplicate_rate": float(config.duplicate_rate).hex(),
            "corrupt_rate": float(config.corrupt_rate).hex(),
            "latency_ms": config.latency_ms,
            "jitter_ms": config.jitter_ms,
            "reorder_window": config.reorder_window,
        },
    }
    return json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def configuration_fingerprint(config: LinkConfig) -> str:
    """Return a versioned SHA-256 fingerprint for an effective configuration."""

    canonical = canonical_effective_config(config).encode("ascii")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"

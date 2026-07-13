"""Deterministic bounded mutation helpers for parser assurance tests."""

from __future__ import annotations

from collections.abc import Mapping


def single_bit_mutations(payload: bytes) -> tuple[bytes, ...]:
    """Flip the least-significant bit of each byte, one byte at a time."""

    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    return tuple(
        payload[:index] + bytes((value ^ 0x01,)) + payload[index + 1 :]
        for index, value in enumerate(payload)
    )


def byte_truncations(payload: bytes) -> tuple[bytes, ...]:
    """Return every strict prefix of a byte payload in stable length order."""

    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    return tuple(payload[:length] for length in range(len(payload)))


def byte_extensions(payload: bytes, *, limit: int = 4) -> tuple[bytes, ...]:
    """Append deterministic non-empty suffixes up to a bounded size."""

    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    if limit < 0:
        raise ValueError("limit must be non-negative")
    return tuple(payload + bytes(range(1, length + 1)) for length in range(1, limit + 1))


def mappings_without_each_key(
    document: Mapping[str, object],
) -> tuple[tuple[str, dict[str, object]], ...]:
    """Remove each top-level key once in deterministic lexical order."""

    return tuple(
        (
            removed,
            {key: value for key, value in document.items() if key != removed},
        )
        for removed in sorted(document)
    )


def bounded_text_truncations(document: str) -> tuple[str, ...]:
    """Return representative strict prefixes without unbounded test growth."""

    if not isinstance(document, str):
        raise TypeError("document must be a string")
    if not document:
        return ()
    cuts = {
        0,
        1,
        len(document) // 4,
        len(document) // 2,
        (3 * len(document)) // 4,
        len(document) - 1,
    }
    return tuple(document[:cut] for cut in sorted(cuts) if 0 <= cut < len(document))

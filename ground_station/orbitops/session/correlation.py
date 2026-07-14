"""Compatibility and correlation semantics for OrbitOps session evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

_MAX_PACKET_SEQUENCE = 0xFFFFFFFF


class EvidenceLane(StrEnum):
    """Independent evidence streams accepted by the session inspector."""

    TELEMETRY = "telemetry"
    ALARM = "alarm"
    LINK = "link"


class CorrelationKind(StrEnum):
    """Strength of one correlation decision."""

    EXACT = "exact"
    ORDERED_ONLY = "ordered_only"
    SEPARATE_LANE = "separate_lane"
    AMBIGUOUS = "ambiguous"
    IMPOSSIBLE = "impossible"


class CorrelationBasis(StrEnum):
    """Stable field or rule supporting a correlation decision."""

    SOURCE_ORDER = "source_order"
    PACKET_SEQUENCE = "packet_sequence"
    NONE = "none"


class SourceCompleteness(StrEnum):
    """What one validated evidence lane can prove about run completion."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ContractSemantics:
    """Compatibility-relevant fields exposed by one evidence contract."""

    lane: EvidenceLane
    readable_schema_versions: tuple[int, ...]
    source_order_field: str
    packet_reference_field: str | None
    session_identity_field: str | None
    time_fields: tuple[str, ...]
    completion_marker: str | None


@dataclass(frozen=True, slots=True)
class CorrelationRule:
    """Permitted outcomes for one pair of evidence lanes."""

    left: EvidenceLane
    right: EvidenceLane
    possible_kinds: tuple[CorrelationKind, ...]
    basis: CorrelationBasis
    shared_clock: bool = False

    def __post_init__(self) -> None:
        if not self.possible_kinds:
            raise ValueError("possible_kinds must not be empty")
        if self.left is self.right and self.possible_kinds != (CorrelationKind.ORDERED_ONLY,):
            raise ValueError("same-lane rules must preserve source order only")
        if self.shared_clock:
            raise ValueError("current OrbitOps evidence lanes do not share a clock domain")


@dataclass(frozen=True, slots=True)
class CorrelationDecision:
    """Result of correlating one alarm transition to loaded telemetry records."""

    kind: CorrelationKind
    basis: CorrelationBasis
    candidate_record_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        candidate_count = len(self.candidate_record_indices)
        if self.kind is CorrelationKind.EXACT and candidate_count != 1:
            raise ValueError("exact correlation requires exactly one candidate")
        if self.kind is CorrelationKind.AMBIGUOUS and candidate_count < 2:
            raise ValueError("ambiguous correlation requires at least two candidates")
        if self.kind not in {CorrelationKind.EXACT, CorrelationKind.AMBIGUOUS} and candidate_count:
            raise ValueError(f"{self.kind.value} correlation cannot contain candidates")
        if tuple(sorted(self.candidate_record_indices)) != self.candidate_record_indices:
            raise ValueError("candidate_record_indices must use deterministic ascending order")
        if any(index < 0 for index in self.candidate_record_indices):
            raise ValueError("candidate_record_indices must be non-negative")


LANE_PRECEDENCE: Final[tuple[EvidenceLane, ...]] = (
    EvidenceLane.TELEMETRY,
    EvidenceLane.ALARM,
    EvidenceLane.LINK,
)
_LANE_RANK: Final[Mapping[EvidenceLane, int]] = MappingProxyType(
    {lane: rank for rank, lane in enumerate(LANE_PRECEDENCE)}
)

_CONTRACT_SEMANTICS: dict[EvidenceLane, ContractSemantics] = {
    EvidenceLane.TELEMETRY: ContractSemantics(
        lane=EvidenceLane.TELEMETRY,
        readable_schema_versions=(1,),
        source_order_field="record_order",
        packet_reference_field="decoded_packet.sequence",
        session_identity_field=None,
        time_fields=("received_at", "decoded_packet.timestamp_ms"),
        completion_marker=None,
    ),
    EvidenceLane.ALARM: ContractSemantics(
        lane=EvidenceLane.ALARM,
        readable_schema_versions=(1,),
        source_order_field="event_index",
        packet_reference_field="packet_sequence",
        session_identity_field="session_id",
        time_fields=("elapsed_ns",),
        completion_marker="run_summary",
    ),
    EvidenceLane.LINK: ContractSemantics(
        lane=EvidenceLane.LINK,
        readable_schema_versions=(1, 2),
        source_order_field="event_index",
        packet_reference_field="packet_index",
        session_identity_field="session_id",
        time_fields=("elapsed_ns",),
        completion_marker="run_summary",
    ),
}
CONTRACT_SEMANTICS: Final[Mapping[EvidenceLane, ContractSemantics]] = MappingProxyType(
    _CONTRACT_SEMANTICS
)


def _pair_key(left: EvidenceLane, right: EvidenceLane) -> tuple[EvidenceLane, EvidenceLane]:
    if _LANE_RANK[left] <= _LANE_RANK[right]:
        return left, right
    return right, left


_PAIR_RULES: dict[tuple[EvidenceLane, EvidenceLane], CorrelationRule] = {
    (EvidenceLane.TELEMETRY, EvidenceLane.ALARM): CorrelationRule(
        left=EvidenceLane.TELEMETRY,
        right=EvidenceLane.ALARM,
        possible_kinds=(
            CorrelationKind.EXACT,
            CorrelationKind.AMBIGUOUS,
            CorrelationKind.IMPOSSIBLE,
        ),
        basis=CorrelationBasis.PACKET_SEQUENCE,
    ),
    (EvidenceLane.TELEMETRY, EvidenceLane.LINK): CorrelationRule(
        left=EvidenceLane.TELEMETRY,
        right=EvidenceLane.LINK,
        possible_kinds=(CorrelationKind.SEPARATE_LANE,),
        basis=CorrelationBasis.NONE,
    ),
    (EvidenceLane.ALARM, EvidenceLane.LINK): CorrelationRule(
        left=EvidenceLane.ALARM,
        right=EvidenceLane.LINK,
        possible_kinds=(CorrelationKind.SEPARATE_LANE,),
        basis=CorrelationBasis.NONE,
    ),
}
PAIR_CORRELATION_RULES: Final[Mapping[tuple[EvidenceLane, EvidenceLane], CorrelationRule]] = (
    MappingProxyType(_PAIR_RULES)
)


def correlation_rule(left: EvidenceLane, right: EvidenceLane) -> CorrelationRule:
    """Return the immutable correlation rule for two lanes."""

    if left is right:
        return CorrelationRule(
            left=left,
            right=right,
            possible_kinds=(CorrelationKind.ORDERED_ONLY,),
            basis=CorrelationBasis.SOURCE_ORDER,
        )
    return PAIR_CORRELATION_RULES[_pair_key(left, right)]


def _validate_packet_sequence(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer")
    if not 0 <= value <= _MAX_PACKET_SEQUENCE:
        raise ValueError(f"{field} must fit an unsigned 32-bit integer")
    return value


def classify_telemetry_alarm_match(
    telemetry_sequences: Sequence[int],
    alarm_packet_sequence: int,
) -> CorrelationDecision:
    """Classify one alarm-to-telemetry match using packet sequence only.

    Packet sequence can prove an exact relationship only when the loaded
    telemetry evidence contains exactly one record with that sequence. A
    missing sequence is impossible to correlate from the loaded evidence, and
    duplicate or wrapped sequences remain visibly ambiguous.
    """

    target = _validate_packet_sequence(
        alarm_packet_sequence,
        field="alarm_packet_sequence",
    )
    candidates: list[int] = []
    for record_index, sequence in enumerate(telemetry_sequences):
        validated = _validate_packet_sequence(
            sequence,
            field=f"telemetry_sequences[{record_index}]",
        )
        if validated == target:
            candidates.append(record_index)

    ordered_candidates = tuple(candidates)
    if len(ordered_candidates) == 1:
        return CorrelationDecision(
            kind=CorrelationKind.EXACT,
            basis=CorrelationBasis.PACKET_SEQUENCE,
            candidate_record_indices=ordered_candidates,
        )
    if len(ordered_candidates) > 1:
        return CorrelationDecision(
            kind=CorrelationKind.AMBIGUOUS,
            basis=CorrelationBasis.PACKET_SEQUENCE,
            candidate_record_indices=ordered_candidates,
        )
    return CorrelationDecision(
        kind=CorrelationKind.IMPOSSIBLE,
        basis=CorrelationBasis.PACKET_SEQUENCE,
    )


def presentation_key(lane: EvidenceLane, source_index: int) -> tuple[int, int]:
    """Return a deterministic presentation key without implying shared time."""

    if isinstance(source_index, bool) or not isinstance(source_index, int):
        raise TypeError("source_index must be an integer")
    if source_index < 0:
        raise ValueError("source_index must be non-negative")
    return _LANE_RANK[lane], source_index


def classify_source_completeness(
    lane: EvidenceLane,
    record_count: int,
    *,
    summary_present: bool = False,
) -> SourceCompleteness:
    """Classify source-local completion without inventing an end marker."""

    if isinstance(record_count, bool) or not isinstance(record_count, int):
        raise TypeError("record_count must be an integer")
    if record_count < 0:
        raise ValueError("record_count must be non-negative")
    if not isinstance(summary_present, bool):
        raise TypeError("summary_present must be a boolean")
    if record_count == 0:
        if summary_present:
            raise ValueError("an empty source cannot contain a summary")
        return SourceCompleteness.INCOMPLETE

    semantics = CONTRACT_SEMANTICS[lane]
    if semantics.completion_marker is None:
        if summary_present:
            raise ValueError(f"{lane.value} evidence has no summary marker")
        return SourceCompleteness.UNKNOWN
    if summary_present:
        return SourceCompleteness.COMPLETE
    return SourceCompleteness.INCOMPLETE

"""Run statistics and deterministic event-stream coordination."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .events import (
    EventAttributes,
    EventSink,
    LinkEvent,
    LinkEventType,
    LinkRunMetadata,
)

_COUNTER_NAMES = (
    "packets_received",
    "packets_dropped",
    "packets_delayed",
    "packets_duplicated",
    "packets_corrupted",
    "packets_reordered",
    "deliveries_scheduled",
    "deliveries_forwarded",
)


@dataclass(frozen=True, slots=True)
class LinkStatistics:
    """Counters derived exclusively from emitted packet and delivery events."""

    packets_received: int = 0
    packets_dropped: int = 0
    packets_delayed: int = 0
    packets_duplicated: int = 0
    packets_corrupted: int = 0
    packets_reordered: int = 0
    deliveries_scheduled: int = 0
    deliveries_forwarded: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "packets_received": self.packets_received,
            "packets_dropped": self.packets_dropped,
            "packets_delayed": self.packets_delayed,
            "packets_duplicated": self.packets_duplicated,
            "packets_corrupted": self.packets_corrupted,
            "packets_reordered": self.packets_reordered,
            "deliveries_scheduled": self.deliveries_scheduled,
            "deliveries_forwarded": self.deliveries_forwarded,
        }

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> LinkStatistics:
        if set(values) != set(_COUNTER_NAMES):
            raise ValueError("run_summary statistics have invalid keys")
        validated: dict[str, int] = {}
        for name in _COUNTER_NAMES:
            value = values[name]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"summary counter {name!r} must be a non-negative integer")
            validated[name] = value
        return _statistics_from_values(validated)


def _statistics_from_values(values: Mapping[str, int]) -> LinkStatistics:
    return LinkStatistics(
        packets_received=values["packets_received"],
        packets_dropped=values["packets_dropped"],
        packets_delayed=values["packets_delayed"],
        packets_duplicated=values["packets_duplicated"],
        packets_corrupted=values["packets_corrupted"],
        packets_reordered=values["packets_reordered"],
        deliveries_scheduled=values["deliveries_scheduled"],
        deliveries_forwarded=values["deliveries_forwarded"],
    )


# RUN_METADATA and RUN_SUMMARY are deliberately absent. Schema 2 adds context
# without changing the packet and delivery counter semantics established in v0.2.
_EVENT_COUNTERS: dict[LinkEventType, str] = {
    LinkEventType.PACKET_RECEIVED: "packets_received",
    LinkEventType.PACKET_DROPPED: "packets_dropped",
    LinkEventType.PACKET_DELAYED: "packets_delayed",
    LinkEventType.PACKET_DUPLICATED: "packets_duplicated",
    LinkEventType.PACKET_CORRUPTED: "packets_corrupted",
    LinkEventType.PACKET_REORDERED: "packets_reordered",
    LinkEventType.DELIVERY_SCHEDULED: "deliveries_scheduled",
    LinkEventType.PACKET_FORWARDED: "deliveries_forwarded",
}


def statistics_from_events(events: Iterable[LinkEvent]) -> LinkStatistics:
    """Derive counters from an event sequence, ignoring metadata and summary events."""

    counters = {name: 0 for name in _COUNTER_NAMES}
    for event in events:
        counter = _EVENT_COUNTERS.get(event.event_type)
        if counter is not None:
            counters[counter] += 1
    return _statistics_from_values(counters)


def _stream_metadata(sequence: tuple[LinkEvent, ...]) -> LinkRunMetadata | None:
    """Validate stream metadata while preserving schema-1 compatibility."""

    if not sequence:
        raise ValueError("event stream is empty")
    schema_versions = {event.schema_version for event in sequence}
    if len(schema_versions) != 1:
        raise ValueError("event stream changed schema_version")
    schema_version = next(iter(schema_versions))
    metadata_events = [
        event for event in sequence if event.event_type is LinkEventType.RUN_METADATA
    ]

    if schema_version == 1:
        if metadata_events:
            raise ValueError("schema version 1 streams may not contain run_metadata")
        return None
    if len(metadata_events) != 1 or sequence[0] is not metadata_events[0]:
        raise ValueError("schema version 2 streams require one leading run_metadata event")
    return LinkRunMetadata.from_attributes(metadata_events[0].attributes)


def run_metadata_from_events(events: Iterable[LinkEvent]) -> LinkRunMetadata | None:
    """Return versioned run metadata, or ``None`` for a legacy schema-1 stream."""

    return _stream_metadata(tuple(events))


def validate_run_summary(events: Iterable[LinkEvent]) -> LinkStatistics:
    """Verify that one complete event stream ends with matching counters."""

    sequence = tuple(events)
    if not sequence or sequence[-1].event_type is not LinkEventType.RUN_SUMMARY:
        raise ValueError("complete event stream must end with run_summary")
    if any(event.event_type is LinkEventType.RUN_SUMMARY for event in sequence[:-1]):
        raise ValueError("run_summary may appear only once")
    _stream_metadata(sequence)

    calculated = statistics_from_events(sequence[:-1])
    recorded = LinkStatistics.from_mapping(sequence[-1].attributes)
    if calculated != recorded:
        raise ValueError("run_summary counters do not match emitted events")
    return calculated


class LinkEventStream:
    """Assign stable indices, relative times, and statistics to emitted events.

    Run metadata occupies event index zero but never contributes to operational
    counters.
    """

    __slots__ = (
        "_closed",
        "_event_index",
        "_last_elapsed_ns",
        "_session_id",
        "_sink",
        "_start_ns",
        "_statistics",
    )

    def __init__(self, session_id: str, start_ns: int, sink: EventSink | None = None) -> None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        if isinstance(start_ns, bool) or not isinstance(start_ns, int):
            raise TypeError("start_ns must be an integer")
        if start_ns < 0:
            raise ValueError("start_ns must be non-negative")
        self._session_id = session_id
        self._start_ns = start_ns
        self._sink = sink
        self._event_index = 0
        self._last_elapsed_ns = 0
        self._statistics = LinkStatistics()
        self._closed = False

    @property
    def statistics(self) -> LinkStatistics:
        return self._statistics

    def _emit(
        self,
        event_type: LinkEventType,
        now_ns: int,
        *,
        packet_index: int | None = None,
        attributes: EventAttributes | None = None,
    ) -> LinkEvent:
        if isinstance(now_ns, bool) or not isinstance(now_ns, int):
            raise TypeError("now_ns must be an integer")
        elapsed_ns = now_ns - self._start_ns
        if elapsed_ns < self._last_elapsed_ns:
            raise ValueError("event clock moved backwards")

        event = LinkEvent(
            session_id=self._session_id,
            event_index=self._event_index,
            elapsed_ns=elapsed_ns,
            event_type=event_type,
            packet_index=packet_index,
            attributes={} if attributes is None else attributes,
        )
        if self._sink is not None:
            self._sink(event)

        # Only packet and delivery events appear in the counter map.
        counter = _EVENT_COUNTERS.get(event_type)
        if counter is not None:
            values = self._statistics.to_dict()
            values[counter] += 1
            self._statistics = _statistics_from_values(values)
        self._event_index += 1
        self._last_elapsed_ns = elapsed_ns
        return event

    def emit_run_metadata(self, metadata: LinkRunMetadata, now_ns: int) -> LinkEvent:
        """Emit the required leading run metadata record."""

        if self._closed:
            raise RuntimeError("event stream is closed")
        if self._event_index != 0:
            raise RuntimeError("run_metadata must be the first event")
        if not isinstance(metadata, LinkRunMetadata):
            raise TypeError("metadata must be a LinkRunMetadata instance")
        return self._emit(
            LinkEventType.RUN_METADATA,
            now_ns,
            attributes=metadata.to_attributes(),
        )

    def emit(
        self,
        event_type: LinkEventType,
        now_ns: int,
        *,
        packet_index: int | None = None,
        attributes: EventAttributes | None = None,
    ) -> LinkEvent:
        if self._closed:
            raise RuntimeError("event stream is closed")
        if self._event_index == 0:
            raise RuntimeError("emit_run_metadata must be called before packet events")
        if event_type is LinkEventType.RUN_METADATA:
            raise ValueError("use emit_run_metadata for the first event")
        if event_type is LinkEventType.RUN_SUMMARY:
            raise ValueError("use emit_summary to close an event stream")
        return self._emit(
            event_type,
            now_ns,
            packet_index=packet_index,
            attributes=attributes,
        )

    def emit_summary(self, now_ns: int) -> LinkEvent:
        if self._closed:
            raise RuntimeError("event stream is closed")
        if self._event_index == 0:
            raise RuntimeError("emit_run_metadata must be called before run_summary")
        event = self._emit(
            LinkEventType.RUN_SUMMARY,
            now_ns,
            attributes=self._statistics.to_dict(),
        )
        self._closed = True
        return event

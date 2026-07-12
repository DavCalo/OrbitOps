from __future__ import annotations

import unittest

from orbitops.link.events import LinkEvent, LinkEventType
from orbitops.link.statistics import (
    LinkEventStream,
    LinkStatistics,
    statistics_from_events,
    validate_run_summary,
)


class LinkStatisticsTests(unittest.TestCase):
    def test_event_stream_assigns_indices_times_and_summary(self) -> None:
        events: list[LinkEvent] = []
        stream = LinkEventStream("session", start_ns=100, sink=events.append)
        stream.emit(LinkEventType.PACKET_RECEIVED, 100, packet_index=0)
        stream.emit(LinkEventType.PACKET_DROPPED, 105, packet_index=0)
        summary = stream.emit_summary(110)

        self.assertEqual([event.event_index for event in events], [0, 1, 2])
        self.assertEqual([event.elapsed_ns for event in events], [0, 5, 10])
        self.assertEqual(summary.attributes["packets_received"], 1)
        self.assertEqual(summary.attributes["packets_dropped"], 1)
        self.assertEqual(validate_run_summary(events), stream.statistics)
        with self.assertRaises(RuntimeError):
            stream.emit(LinkEventType.PACKET_RECEIVED, 111)

    def test_statistics_are_derived_only_from_non_summary_events(self) -> None:
        events = [
            LinkEvent("s", 0, 0, LinkEventType.PACKET_RECEIVED),
            LinkEvent("s", 1, 0, LinkEventType.PACKET_DUPLICATED),
            LinkEvent("s", 2, 0, LinkEventType.DELIVERY_SCHEDULED),
            LinkEvent("s", 3, 0, LinkEventType.DELIVERY_SCHEDULED),
            LinkEvent("s", 4, 0, LinkEventType.PACKET_FORWARDED),
            LinkEvent("s", 5, 0, LinkEventType.PACKET_FORWARDED),
            LinkEvent("s", 6, 0, LinkEventType.RUN_SUMMARY),
        ]
        self.assertEqual(
            statistics_from_events(events),
            LinkStatistics(
                packets_received=1,
                packets_duplicated=1,
                deliveries_scheduled=2,
                deliveries_forwarded=2,
            ),
        )

    def test_summary_validation_rejects_missing_or_mismatched_summary(self) -> None:
        received = LinkEvent("s", 0, 0, LinkEventType.PACKET_RECEIVED)
        with self.assertRaisesRegex(ValueError, "run_summary"):
            validate_run_summary([received])

        mismatched = LinkEvent(
            "s",
            1,
            1,
            LinkEventType.RUN_SUMMARY,
            attributes=LinkStatistics().to_dict(),
        )
        with self.assertRaisesRegex(ValueError, "do not match"):
            validate_run_summary([received, mismatched])

    def test_stream_validates_time_and_identity(self) -> None:
        with self.assertRaises(ValueError):
            LinkEventStream("", 0)
        with self.assertRaises(TypeError):
            LinkEventStream("session", True)
        stream = LinkEventStream("session", 10)
        stream.emit(LinkEventType.PACKET_RECEIVED, 12)
        with self.assertRaises(ValueError):
            stream.emit(LinkEventType.PACKET_DROPPED, 11)

    def test_statistics_mapping_is_strict(self) -> None:
        values = LinkStatistics(packets_received=2).to_dict()
        self.assertEqual(LinkStatistics.from_mapping(values).packets_received, 2)
        with self.assertRaises(ValueError):
            LinkStatistics.from_mapping({"packets_received": 1})
        values["packets_received"] = -1
        with self.assertRaises(ValueError):
            LinkStatistics.from_mapping(values)


if __name__ == "__main__":
    unittest.main()

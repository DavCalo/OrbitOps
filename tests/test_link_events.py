from __future__ import annotations

import json
import socket
import tempfile
import threading
import unittest
from collections.abc import Mapping
from pathlib import Path

from orbitops.link import (
    JsonlEventRecorder,
    LinkConfig,
    LinkEvent,
    LinkEventType,
    LinkRunMetadata,
    LinkRuntime,
    LinkStatistics,
    configuration_fingerprint,
    load_link_events,
    run_metadata_from_events,
    validate_run_summary,
)
from orbitops.link.decisions import Delivery, PacketOutcome
from orbitops.link.impairments import ImpairmentEngine


class StubImpairmentEngine(ImpairmentEngine):
    __slots__ = ("_outcomes",)

    def __init__(self, outcomes: list[PacketOutcome]) -> None:
        super().__init__(LinkConfig())
        self._outcomes = iter(outcomes)

    def process(self, payload: bytes) -> PacketOutcome:
        del payload
        return next(self._outcomes)


class LinkEventTests(unittest.TestCase):
    def legacy_event(
        self,
        index: int,
        event_type: LinkEventType,
        elapsed_ns: int = 0,
        *,
        attributes: Mapping[str, str | int | float | bool | None] | None = None,
    ) -> LinkEvent:
        return LinkEvent(
            session_id="session-1",
            event_index=index,
            elapsed_ns=elapsed_ns,
            event_type=event_type,
            attributes={} if attributes is None else attributes,
            schema_version=1,
        )

    def test_schema_version_two_run_metadata_round_trip_is_canonical(self) -> None:
        metadata = LinkRunMetadata(
            configuration_fingerprint(LinkConfig(seed=7)),
            profile_name="nominal",
            profile_reference="builtin:nominal",
            profile_schema_version=1,
        )
        events = (
            LinkEvent(
                session_id="session-2",
                event_index=0,
                elapsed_ns=0,
                event_type=LinkEventType.RUN_METADATA,
                attributes=metadata.to_attributes(),
            ),
            LinkEvent(
                session_id="session-2",
                event_index=1,
                elapsed_ns=12,
                event_type=LinkEventType.RUN_SUMMARY,
                attributes=LinkStatistics().to_dict(),
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            with JsonlEventRecorder(path) as recorder:
                for event in events:
                    recorder.write(event)

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                lines,
                [
                    json.dumps(event.to_dict(), separators=(",", ":"), sort_keys=True)
                    for event in events
                ],
            )
            loaded = load_link_events(path)
            self.assertEqual(loaded, events)
            self.assertEqual(run_metadata_from_events(loaded), metadata)
            self.assertEqual(validate_run_summary(loaded), LinkStatistics())
            with self.assertRaises(RuntimeError):
                recorder.write(events[0])

    def test_legacy_schema_one_log_remains_readable(self) -> None:
        records = (
            self.legacy_event(0, LinkEventType.PACKET_RECEIVED),
            self.legacy_event(
                1,
                LinkEventType.RUN_SUMMARY,
                1,
                attributes=LinkStatistics(packets_received=1).to_dict(),
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.jsonl"
            path.write_text(
                "".join(json.dumps(event.to_dict()) + "\n" for event in records),
                encoding="utf-8",
            )
            loaded = load_link_events(path)

        self.assertEqual(loaded, records)
        self.assertIsNone(run_metadata_from_events(loaded))
        self.assertEqual(validate_run_summary(loaded).packets_received, 1)

    def test_load_rejects_malformed_legacy_sequences(self) -> None:
        cases = {
            "invalid-json": "{\n",
            "missing-key": json.dumps({"schema_version": 1}) + "\n",
            "wrong-index": json.dumps(self.legacy_event(2, LinkEventType.PACKET_RECEIVED).to_dict())
            + "\n",
            "mixed-session": "".join(
                [
                    json.dumps(self.legacy_event(0, LinkEventType.PACKET_RECEIVED).to_dict())
                    + "\n",
                    json.dumps(
                        LinkEvent(
                            session_id="session-2",
                            event_index=1,
                            elapsed_ns=0,
                            event_type=LinkEventType.PACKET_DROPPED,
                            schema_version=1,
                        ).to_dict()
                    )
                    + "\n",
                ]
            ),
            "time-backwards": "".join(
                [
                    json.dumps(
                        self.legacy_event(
                            0,
                            LinkEventType.PACKET_RECEIVED,
                            2,
                        ).to_dict()
                    )
                    + "\n",
                    json.dumps(
                        self.legacy_event(
                            1,
                            LinkEventType.PACKET_DROPPED,
                            1,
                        ).to_dict()
                    )
                    + "\n",
                ]
            ),
            "after-summary": "".join(
                [
                    json.dumps(self.legacy_event(0, LinkEventType.RUN_SUMMARY).to_dict()) + "\n",
                    json.dumps(self.legacy_event(1, LinkEventType.PACKET_RECEIVED).to_dict())
                    + "\n",
                ]
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, content in cases.items():
                with self.subTest(name=name):
                    path = Path(directory) / f"{name}.jsonl"
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_link_events(path)

    def test_load_accepts_version_two_partial_log_with_metadata(self) -> None:
        metadata = LinkRunMetadata(configuration_fingerprint(LinkConfig()))
        record = LinkEvent(
            session_id="partial",
            event_index=0,
            elapsed_ns=0,
            event_type=LinkEventType.RUN_METADATA,
            attributes=metadata.to_attributes(),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "partial.jsonl"
            path.write_text(json.dumps(record.to_dict()) + "\n", encoding="utf-8")
            self.assertEqual(load_link_events(path), (record,))

    def test_load_rejects_invalid_metadata_order_and_schema_changes(self) -> None:
        metadata = LinkRunMetadata(configuration_fingerprint(LinkConfig()))
        cases = {
            "missing-metadata": LinkEvent(
                "session",
                0,
                0,
                LinkEventType.PACKET_RECEIVED,
            ).to_dict(),
            "duplicate-metadata": [
                LinkEvent(
                    "session",
                    0,
                    0,
                    LinkEventType.RUN_METADATA,
                    attributes=metadata.to_attributes(),
                ).to_dict(),
                LinkEvent(
                    "session",
                    1,
                    0,
                    LinkEventType.RUN_METADATA,
                    attributes=metadata.to_attributes(),
                ).to_dict(),
            ],
            "mixed-schema": [
                self.legacy_event(0, LinkEventType.PACKET_RECEIVED).to_dict(),
                LinkEvent(
                    "session-1",
                    1,
                    0,
                    LinkEventType.RUN_SUMMARY,
                    attributes=LinkStatistics(packets_received=1).to_dict(),
                ).to_dict(),
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, payload in cases.items():
                with self.subTest(name=name):
                    records = payload if isinstance(payload, list) else [payload]
                    path = Path(directory) / f"{name}.jsonl"
                    path.write_text(
                        "".join(json.dumps(record) + "\n" for record in records),
                        encoding="utf-8",
                    )
                    with self.assertRaises(ValueError):
                        load_link_events(path)

    def test_metadata_validation_is_strict(self) -> None:
        fingerprint = configuration_fingerprint(LinkConfig())
        with self.assertRaises(ValueError):
            LinkRunMetadata("sha256:not-hex")
        with self.assertRaises(ValueError):
            LinkRunMetadata(fingerprint, profile_name="nominal")
        with self.assertRaises(ValueError):
            LinkEvent(
                "session",
                0,
                0,
                LinkEventType.RUN_METADATA,
                attributes={
                    "configuration_fingerprint": fingerprint,
                    "profile_name": None,
                    "profile_reference": None,
                },
            )
        with self.assertRaises(ValueError):
            LinkEvent(
                "session",
                0,
                0,
                LinkEventType.RUN_METADATA,
                attributes=LinkRunMetadata(fingerprint).to_attributes(),
                schema_version=1,
            )

    def test_event_validation_rejects_invalid_fields(self) -> None:
        with self.assertRaises(ValueError):
            LinkEvent("", 0, 0, LinkEventType.PACKET_RECEIVED)
        with self.assertRaises(ValueError):
            LinkEvent("session", -1, 0, LinkEventType.PACKET_RECEIVED)
        with self.assertRaises(ValueError):
            LinkEvent(
                "session",
                0,
                0,
                LinkEventType.PACKET_RECEIVED,
                attributes={"not_finite": float("nan")},
            )
        with self.assertRaises(ValueError):
            LinkEvent(
                "session",
                0,
                0,
                LinkEventType.PACKET_RECEIVED,
                schema_version=99,
            )


class LinkRuntimeEventTests(unittest.TestCase):
    def receiver(self) -> socket.socket:
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(2.0)
        return receiver

    def run_one(
        self,
        config: LinkConfig,
        payload: bytes,
        *,
        metadata: LinkRunMetadata | None = None,
    ) -> tuple[list[bytes], list[LinkEvent]]:
        events: list[LinkEvent] = []
        with self.receiver() as receiver:
            runtime = LinkRuntime(
                ("127.0.0.1", 0),
                receiver.getsockname(),
                config,
                event_sink=events.append,
                session_id="runtime-test",
                run_metadata=metadata,
            )
            runtime.open()
            address = runtime.bound_address
            thread = threading.Thread(target=runtime.run, kwargs={"max_packets": 1})
            thread.start()
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                sender.sendto(payload, address)

            expected = 2 if config.duplicate_rate == 1.0 and config.loss_rate == 0.0 else 1
            received: list[bytes] = []
            if config.loss_rate == 0.0:
                for _ in range(expected):
                    received.append(receiver.recvfrom(4096)[0])
            thread.join(timeout=2.0)
            self.assertFalse(thread.is_alive())
            validate_run_summary(events)
            self.assertEqual(runtime.statistics, validate_run_summary(events))
            return received, events

    def test_empty_run_emits_metadata_and_zero_summary(self) -> None:
        events: list[LinkEvent] = []
        stop = threading.Event()
        stop.set()
        runtime = LinkRuntime(
            ("127.0.0.1", 0),
            ("127.0.0.1", 9),
            LinkConfig(),
            event_sink=events.append,
            session_id="empty",
        )
        runtime.open()
        runtime.run(stop_event=stop)
        self.assertEqual(
            [event.event_type for event in events],
            [LinkEventType.RUN_METADATA, LinkEventType.RUN_SUMMARY],
        )
        metadata = run_metadata_from_events(events)
        self.assertIsNotNone(metadata)
        assert metadata is not None
        self.assertEqual(
            metadata.configuration_fingerprint,
            configuration_fingerprint(LinkConfig()),
        )
        self.assertEqual(validate_run_summary(events).packets_received, 0)

    def test_nominal_run_preserves_packet_event_semantics(self) -> None:
        received, events = self.run_one(LinkConfig(), b"orbitops")
        self.assertEqual(received, [b"orbitops"])
        self.assertEqual(
            [event.event_type for event in events],
            [
                LinkEventType.RUN_METADATA,
                LinkEventType.PACKET_RECEIVED,
                LinkEventType.DELIVERY_SCHEDULED,
                LinkEventType.PACKET_FORWARDED,
                LinkEventType.RUN_SUMMARY,
            ],
        )
        statistics = validate_run_summary(events)
        self.assertEqual(statistics.packets_received, 1)
        self.assertEqual(statistics.deliveries_scheduled, 1)
        self.assertEqual(statistics.deliveries_forwarded, 1)

    def test_runtime_jsonl_log_is_complete_and_replayable(self) -> None:
        with tempfile.TemporaryDirectory() as directory, self.receiver() as receiver:
            path = Path(directory) / "runtime-events.jsonl"
            with JsonlEventRecorder(path) as recorder:
                runtime = LinkRuntime(
                    ("127.0.0.1", 0),
                    receiver.getsockname(),
                    LinkConfig(),
                    event_sink=recorder.write,
                    session_id="jsonl-runtime",
                )
                runtime.open()
                thread = threading.Thread(
                    target=runtime.run,
                    kwargs={"max_packets": 1},
                )
                thread.start()
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    sender.sendto(b"recorded", runtime.bound_address)
                self.assertEqual(receiver.recvfrom(4096)[0], b"recorded")
                thread.join(timeout=2.0)
                self.assertFalse(thread.is_alive())

            events = load_link_events(path)
            self.assertEqual(events[0].event_type, LinkEventType.RUN_METADATA)
            self.assertEqual(events[-1].event_type, LinkEventType.RUN_SUMMARY)
            self.assertEqual(events[0].session_id, "jsonl-runtime")
            self.assertEqual(validate_run_summary(events).deliveries_forwarded, 1)

    def test_runtime_preserves_supplied_profile_identity(self) -> None:
        config = LinkConfig(seed=42, latency_ms=5)
        metadata = LinkRunMetadata(
            configuration_fingerprint(config),
            profile_name="degraded-link",
            profile_reference="builtin:degraded-link",
            profile_schema_version=1,
        )
        _received, events = self.run_one(config, b"profile", metadata=metadata)
        self.assertEqual(run_metadata_from_events(events), metadata)

    def test_runtime_rejects_metadata_for_a_different_configuration(self) -> None:
        metadata = LinkRunMetadata(configuration_fingerprint(LinkConfig()))
        with self.assertRaisesRegex(ValueError, "does not match"):
            LinkRuntime(
                ("127.0.0.1", 0),
                ("127.0.0.1", 9),
                LinkConfig(seed=1),
                run_metadata=metadata,
            )

    def test_impaired_and_dropped_counters_remain_compatible(self) -> None:
        received, events = self.run_one(
            LinkConfig(seed=7, duplicate_rate=1.0, corrupt_rate=1.0, latency_ms=1),
            b"payload",
        )
        self.assertEqual(len(received), 2)
        event_types = [event.event_type for event in events]
        self.assertIn(LinkEventType.PACKET_DUPLICATED, event_types)
        self.assertIn(LinkEventType.PACKET_CORRUPTED, event_types)
        self.assertIn(LinkEventType.PACKET_DELAYED, event_types)
        statistics = validate_run_summary(events)
        self.assertEqual(statistics.packets_duplicated, 1)
        self.assertEqual(statistics.packets_corrupted, 1)
        self.assertEqual(statistics.packets_delayed, 1)

        _received, dropped_events = self.run_one(LinkConfig(loss_rate=1.0), b"lost")
        self.assertEqual(
            [event.event_type for event in dropped_events],
            [
                LinkEventType.RUN_METADATA,
                LinkEventType.PACKET_RECEIVED,
                LinkEventType.PACKET_DROPPED,
                LinkEventType.RUN_SUMMARY,
            ],
        )

    def test_actual_overtake_emits_one_reordered_event(self) -> None:
        events: list[LinkEvent] = []
        outcomes = [
            PacketOutcome(
                packet_index=0,
                dropped=False,
                deliveries=(Delivery(b"zero", 0, 0, 2, None),),
            ),
            PacketOutcome(
                packet_index=1,
                dropped=False,
                deliveries=(Delivery(b"one", 0, 0, 0, None),),
            ),
            PacketOutcome(packet_index=2, dropped=True, deliveries=()),
        ]
        with self.receiver() as receiver:
            runtime = LinkRuntime(
                ("127.0.0.1", 0),
                receiver.getsockname(),
                LinkConfig(),
                event_sink=events.append,
                session_id="reorder",
            )
            runtime.open()
            runtime.engine = StubImpairmentEngine(outcomes)
            address = runtime.bound_address
            thread = threading.Thread(target=runtime.run, kwargs={"max_packets": 3})
            thread.start()
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                for payload in (b"input-0", b"input-1", b"input-2"):
                    sender.sendto(payload, address)
            forwarded = [receiver.recvfrom(4096)[0], receiver.recvfrom(4096)[0]]
            thread.join(timeout=2.0)

        self.assertEqual(forwarded, [b"one", b"zero"])
        reordered = [
            event for event in events if event.event_type is LinkEventType.PACKET_REORDERED
        ]
        self.assertEqual(len(reordered), 1)
        self.assertEqual(reordered[0].packet_index, 0)
        self.assertEqual(validate_run_summary(events).packets_reordered, 1)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.alarm_events import (  # noqa: E402
    ALARM_EVENT_SCHEMA_VERSION,
    AlarmEvent,
    AlarmEventRecorder,
    AlarmEventType,
    AlarmRunMetadata,
    AlarmRunStatistics,
    load_alarm_events,
    run_metadata_from_events,
    statistics_from_events,
    validate_run_summary,
)
from orbitops.alarm_policies import (  # noqa: E402
    ALARM_POLICY_SCHEMA_VERSION,
    AlarmPolicy,
    BatteryAlarmPolicy,
    ModeAlarmPolicy,
    SequenceAlarmPolicy,
    TemperatureAlarmPolicy,
    alarm_policy_fingerprint,
)
from orbitops.alarms import (  # noqa: E402
    AlarmIdentity,
    AlarmSeverity,
    AlarmTransition,
    AlarmTransitionType,
)


class IncrementingClock:
    def __init__(self, start: int = 100) -> None:
        self.value = start

    def __call__(self) -> int:
        self.value += 10
        return self.value


def sample_policy() -> AlarmPolicy:
    return AlarmPolicy(
        schema_version=ALARM_POLICY_SCHEMA_VERSION,
        name="thermal-demo",
        description="Test alarm policy.",
        temperature=TemperatureAlarmPolicy(
            warning_c=30.0,
            critical_c=38.0,
            hysteresis_c=2.0,
        ),
        battery=BatteryAlarmPolicy(
            critical_v=7.0,
            hysteresis_v=0.1,
        ),
        mode=ModeAlarmPolicy(alarm_on_safe=True),
        sequence=SequenceAlarmPolicy(detect_gaps=True),
    )


def sample_transition(
    transition: AlarmTransitionType = AlarmTransitionType.RAISED,
) -> AlarmTransition:
    return AlarmTransition(
        severity=AlarmSeverity.WARNING,
        code="ELEVATED_TEMPERATURE",
        message="temperature is 31.00 °C",
        identity=AlarmIdentity("temperature"),
        transition=transition,
        observed_value=31.0,
        threshold=30.0,
    )


def metadata_event(*, session_id: str = "session") -> AlarmEvent:
    metadata = AlarmRunMetadata.from_policy(
        sample_policy(),
        reference="thermal-demo",
    )
    return AlarmEvent(
        session_id=session_id,
        event_index=0,
        elapsed_ns=0,
        event_type=AlarmEventType.RUN_METADATA,
        attributes=metadata.to_attributes(),
    )


def write_events(path: Path, events: list[AlarmEvent]) -> None:
    path.write_text(
        "".join(
            json.dumps(event.to_dict(), separators=(",", ":"), sort_keys=True) + "\n"
            for event in events
        ),
        encoding="utf-8",
    )


class AlarmEventTests(unittest.TestCase):
    def test_metadata_from_policy_records_identity_and_fingerprint(self) -> None:
        policy = sample_policy()
        metadata = AlarmRunMetadata.from_policy(
            policy,
            reference="builtin:thermal-demo",
        )

        self.assertEqual(metadata.policy_name, "thermal-demo")
        self.assertEqual(metadata.policy_reference, "builtin:thermal-demo")
        self.assertEqual(metadata.policy_schema_version, ALARM_POLICY_SCHEMA_VERSION)
        self.assertEqual(
            metadata.policy_fingerprint,
            alarm_policy_fingerprint(policy),
        )

    def test_metadata_rejects_partial_or_invalid_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "policy_reference"):
            AlarmRunMetadata(
                policy_name="thermal-demo",
                policy_reference="",
                policy_schema_version=1,
                policy_fingerprint="sha256:" + "0" * 64,
            )
        with self.assertRaisesRegex(ValueError, "policy_fingerprint"):
            AlarmRunMetadata(
                policy_name="thermal-demo",
                policy_reference="thermal-demo",
                policy_schema_version=1,
                policy_fingerprint="not-a-fingerprint",
            )

    def test_statistics_increment_and_total(self) -> None:
        statistics = AlarmRunStatistics()
        statistics = statistics.with_transition(AlarmTransitionType.RAISED)
        statistics = statistics.with_transition(AlarmTransitionType.UPDATED)
        statistics = statistics.with_transition(AlarmTransitionType.CLEARED)

        self.assertEqual(statistics, AlarmRunStatistics(1, 1, 1))
        self.assertEqual(statistics.transitions_total, 3)
        self.assertEqual(
            AlarmRunStatistics.from_attributes(statistics.to_attributes()),
            statistics,
        )

    def test_statistics_reject_inconsistent_total(self) -> None:
        with self.assertRaisesRegex(ValueError, "transitions_total"):
            AlarmRunStatistics.from_attributes(
                {
                    "transitions_raised": 1,
                    "transitions_updated": 0,
                    "transitions_cleared": 0,
                    "transitions_total": 2,
                }
            )

    def test_transition_event_round_trip(self) -> None:
        event = AlarmEvent.from_transition(
            session_id="session",
            event_index=1,
            elapsed_ns=25,
            packet_sequence=7,
            transition=sample_transition(),
        )

        self.assertEqual(event.event_type, AlarmEventType.ALARM_RAISED)
        self.assertEqual(event.packet_sequence, 7)
        self.assertNotIn("packet_hex", event.to_dict())
        self.assertEqual(AlarmEvent.from_dict(event.to_dict()), event)

    def test_transition_types_map_to_stable_event_names(self) -> None:
        event_types = [
            AlarmEvent.from_transition(
                session_id="session",
                event_index=index,
                elapsed_ns=index,
                packet_sequence=1,
                transition=sample_transition(transition),
            ).event_type
            for index, transition in enumerate(
                (
                    AlarmTransitionType.RAISED,
                    AlarmTransitionType.UPDATED,
                    AlarmTransitionType.CLEARED,
                )
            )
        ]
        self.assertEqual(
            event_types,
            [
                AlarmEventType.ALARM_RAISED,
                AlarmEventType.ALARM_UPDATED,
                AlarmEventType.ALARM_CLEARED,
            ],
        )

    def test_transition_requires_packet_sequence(self) -> None:
        with self.assertRaisesRegex(ValueError, "packet_sequence"):
            AlarmEvent(
                session_id="session",
                event_index=1,
                elapsed_ns=0,
                event_type=AlarmEventType.ALARM_RAISED,
                attributes=AlarmEvent.from_transition(
                    session_id="session",
                    event_index=1,
                    elapsed_ns=0,
                    packet_sequence=1,
                    transition=sample_transition(),
                ).attributes,
            )

    def test_transition_rejects_invalid_sequence_and_nonfinite_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsigned 32-bit"):
            AlarmEvent.from_transition(
                session_id="session",
                event_index=1,
                elapsed_ns=0,
                packet_sequence=0x1_0000_0000,
                transition=sample_transition(),
            )

        payload = AlarmEvent.from_transition(
            session_id="session",
            event_index=1,
            elapsed_ns=0,
            packet_sequence=1,
            transition=sample_transition(),
        ).to_dict()
        raw_attributes = payload["attributes"]
        if not isinstance(raw_attributes, dict):
            self.fail("alarm-event attributes must be a dictionary")
        attributes = dict(raw_attributes)
        attributes["observed_value"] = math.inf
        payload["attributes"] = attributes
        with self.assertRaisesRegex(ValueError, "finite"):
            AlarmEvent.from_dict(payload)

    def test_event_rejects_unknown_keys_and_boolean_indices(self) -> None:
        payload = metadata_event().to_dict()
        payload["extra"] = True
        with self.assertRaisesRegex(ValueError, "extra"):
            AlarmEvent.from_dict(payload)

        payload = metadata_event().to_dict()
        payload["event_index"] = True
        with self.assertRaisesRegex(ValueError, "event_index"):
            AlarmEvent.from_dict(payload)

    def test_recorder_emits_metadata_transitions_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "alarms.jsonl"
            metadata = AlarmRunMetadata.from_policy(
                sample_policy(),
                reference="thermal-demo",
            )
            with AlarmEventRecorder(
                path,
                metadata,
                session_id="alarm-demo",
                clock_ns=IncrementingClock(),
            ) as recorder:
                recorder.write_transitions(
                    7,
                    [
                        sample_transition(AlarmTransitionType.RAISED),
                        sample_transition(AlarmTransitionType.UPDATED),
                        sample_transition(AlarmTransitionType.CLEARED),
                    ],
                )

            events = load_alarm_events(path)
            self.assertEqual(
                [event.event_type for event in events],
                [
                    AlarmEventType.RUN_METADATA,
                    AlarmEventType.ALARM_RAISED,
                    AlarmEventType.ALARM_UPDATED,
                    AlarmEventType.ALARM_CLEARED,
                    AlarmEventType.RUN_SUMMARY,
                ],
            )
            self.assertEqual(validate_run_summary(events), AlarmRunStatistics(1, 1, 1))
            self.assertEqual(
                run_metadata_from_events(events),
                metadata,
            )

    def test_recorder_close_is_idempotent_and_write_after_close_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "alarms.jsonl"
            recorder = AlarmEventRecorder(
                path,
                AlarmRunMetadata.from_policy(
                    sample_policy(),
                    reference="thermal-demo",
                ),
                session_id="session",
                clock_ns=IncrementingClock(),
            )
            recorder.close()
            original = path.read_text(encoding="utf-8")
            recorder.close()
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            with self.assertRaisesRegex(RuntimeError, "closed"):
                recorder.write_transitions(1, [sample_transition()])

    def test_loader_accepts_metadata_only_partial_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "partial.jsonl"
            write_events(path, [metadata_event()])
            events = load_alarm_events(path)
            self.assertEqual(events, (metadata_event(),))
            with self.assertRaisesRegex(ValueError, "run_summary"):
                validate_run_summary(events)

    def test_loader_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.jsonl"
            path.write_text("{invalid}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 1"):
                load_alarm_events(path)

    def test_loader_rejects_noncontiguous_indices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.jsonl"
            transition = AlarmEvent.from_transition(
                session_id="session",
                event_index=2,
                elapsed_ns=1,
                packet_sequence=1,
                transition=sample_transition(),
            )
            write_events(path, [metadata_event(), transition])
            with self.assertRaisesRegex(ValueError, "non-contiguous"):
                load_alarm_events(path)

    def test_loader_rejects_session_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.jsonl"
            transition = AlarmEvent.from_transition(
                session_id="other",
                event_index=1,
                elapsed_ns=1,
                packet_sequence=1,
                transition=sample_transition(),
            )
            write_events(path, [metadata_event(), transition])
            with self.assertRaisesRegex(ValueError, "session_id changed"):
                load_alarm_events(path)

    def test_loader_rejects_elapsed_time_regression(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.jsonl"
            first = AlarmEvent.from_transition(
                session_id="session",
                event_index=1,
                elapsed_ns=10,
                packet_sequence=1,
                transition=sample_transition(),
            )
            second = AlarmEvent.from_transition(
                session_id="session",
                event_index=2,
                elapsed_ns=9,
                packet_sequence=2,
                transition=sample_transition(),
            )
            write_events(path, [metadata_event(), first, second])
            with self.assertRaisesRegex(ValueError, "moved backwards"):
                load_alarm_events(path)

    def test_loader_requires_unique_leading_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.jsonl"
            write_events(
                path,
                [
                    AlarmEvent.from_transition(
                        session_id="session",
                        event_index=0,
                        elapsed_ns=0,
                        packet_sequence=1,
                        transition=sample_transition(),
                    )
                ],
            )
            with self.assertRaisesRegex(ValueError, "begin with run_metadata"):
                load_alarm_events(path)

            path = Path(directory) / "duplicate.jsonl"
            duplicate = AlarmEvent(
                session_id="session",
                event_index=1,
                elapsed_ns=1,
                event_type=AlarmEventType.RUN_METADATA,
                attributes=AlarmRunMetadata.from_policy(
                    sample_policy(),
                    reference="thermal-demo",
                ).to_attributes(),
            )
            write_events(path, [metadata_event(), duplicate])
            with self.assertRaisesRegex(ValueError, "only once"):
                load_alarm_events(path)

    def test_loader_requires_summary_to_be_final(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.jsonl"
            summary = AlarmEvent(
                session_id="session",
                event_index=1,
                elapsed_ns=1,
                event_type=AlarmEventType.RUN_SUMMARY,
                attributes=AlarmRunStatistics().to_attributes(),
            )
            transition = AlarmEvent.from_transition(
                session_id="session",
                event_index=2,
                elapsed_ns=2,
                packet_sequence=1,
                transition=sample_transition(),
            )
            write_events(path, [metadata_event(), summary, transition])
            with self.assertRaisesRegex(ValueError, "final event"):
                load_alarm_events(path)

    def test_loader_rejects_summary_counter_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.jsonl"
            summary = AlarmEvent(
                session_id="session",
                event_index=1,
                elapsed_ns=1,
                event_type=AlarmEventType.RUN_SUMMARY,
                attributes=AlarmRunStatistics(1, 0, 0).to_attributes(),
            )
            write_events(path, [metadata_event(), summary])
            with self.assertRaisesRegex(ValueError, "do not match"):
                load_alarm_events(path)

    def test_statistics_ignore_metadata_and_summary(self) -> None:
        events = [
            metadata_event(),
            AlarmEvent.from_transition(
                session_id="session",
                event_index=1,
                elapsed_ns=1,
                packet_sequence=1,
                transition=sample_transition(),
            ),
            AlarmEvent(
                session_id="session",
                event_index=2,
                elapsed_ns=2,
                event_type=AlarmEventType.RUN_SUMMARY,
                attributes=AlarmRunStatistics(1, 0, 0).to_attributes(),
            ),
        ]
        self.assertEqual(statistics_from_events(events), AlarmRunStatistics(1, 0, 0))

    def test_schema_version_is_explicit_and_strict(self) -> None:
        self.assertEqual(ALARM_EVENT_SCHEMA_VERSION, 1)
        payload = metadata_event().to_dict()
        payload["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "unsupported"):
            AlarmEvent.from_dict(payload)


if __name__ == "__main__":
    unittest.main()

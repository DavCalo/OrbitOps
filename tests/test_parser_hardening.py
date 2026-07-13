from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "ground_station"))
sys.path.insert(0, str(TESTS))

from orbitops.alarm_events import (  # noqa: E402
    AlarmEvent,
    AlarmEventType,
    load_alarm_events,
)
from orbitops.alarm_policies import (  # noqa: E402
    alarm_policy_fingerprint,
    parse_alarm_policy,
)
from orbitops.link import LinkEvent, LinkEventType, load_link_events  # noqa: E402
from orbitops.profiles import configuration_fingerprint, parse_mission_profile  # noqa: E402
from orbitops.protocol import (  # noqa: E402
    Mode,
    ProtocolError,
    TelemetryPacket,
    decode_packet,
    encode_packet,
)
from orbitops.recorder import iter_records  # noqa: E402
from parser_mutations import (  # noqa: E402
    bounded_text_truncations,
    byte_extensions,
    byte_truncations,
    mappings_without_each_key,
    single_bit_mutations,
)

CORPUS = ROOT / "tests/fixtures/parser_corpus"


def telemetry_packet(
    *,
    sequence: int = 7,
    timestamp_ms: int = 123456,
    mode: Mode = Mode.NOMINAL,
    battery_mv: int = 8100,
    bus_current_ma: int = 420,
    temperature_centi_c: int = 2450,
    roll_centi_deg: int = -120,
    pitch_centi_deg: int = 230,
    yaw_centi_deg: int = 340,
) -> TelemetryPacket:
    return TelemetryPacket(
        sequence=sequence,
        timestamp_ms=timestamp_ms,
        mode=mode,
        battery_mv=battery_mv,
        bus_current_ma=bus_current_ma,
        temperature_centi_c=temperature_centi_c,
        roll_centi_deg=roll_centi_deg,
        pitch_centi_deg=pitch_centi_deg,
        yaw_centi_deg=yaw_centi_deg,
    )


class MutationHelperTests(unittest.TestCase):
    def test_byte_mutations_are_stable_and_bounded(self) -> None:
        payload = b"\x00\x10\xff"
        self.assertEqual(
            single_bit_mutations(payload),
            (b"\x01\x10\xff", b"\x00\x11\xff", b"\x00\x10\xfe"),
        )
        self.assertEqual(byte_truncations(payload), (b"", b"\x00", b"\x00\x10"))
        self.assertEqual(
            byte_extensions(payload, limit=2),
            (payload + b"\x01", payload + b"\x01\x02"),
        )

    def test_mapping_and_text_mutations_are_deterministic(self) -> None:
        mutations = mappings_without_each_key({"beta": 2, "alpha": 1})
        self.assertEqual([name for name, _document in mutations], ["alpha", "beta"])
        self.assertEqual(mutations[0][1], {"beta": 2})
        self.assertEqual(
            bounded_text_truncations("abcdefgh"),
            ("", "a", "ab", "abcd", "abcdef", "abcdefg"),
        )


class ProtocolParserHardeningTests(unittest.TestCase):
    def test_boundary_packets_round_trip(self) -> None:
        packets = (
            telemetry_packet(),
            telemetry_packet(
                sequence=0,
                timestamp_ms=0,
                mode=Mode.BOOT,
                battery_mv=0,
                bus_current_ma=0,
                temperature_centi_c=-0x8000,
                roll_centi_deg=-0x8000,
                pitch_centi_deg=0x7FFF,
                yaw_centi_deg=0,
            ),
            telemetry_packet(
                sequence=0xFFFFFFFF,
                timestamp_ms=0xFFFFFFFFFFFFFFFF,
                mode=Mode.SAFE,
                battery_mv=0xFFFF,
                bus_current_ma=0xFFFF,
                temperature_centi_c=0x7FFF,
                roll_centi_deg=0x7FFF,
                pitch_centi_deg=-0x8000,
                yaw_centi_deg=-0x8000,
            ),
        )
        for packet in packets:
            with self.subTest(sequence=packet.sequence, mode=packet.mode):
                self.assertEqual(decode_packet(encode_packet(packet)), packet)

    def test_every_single_byte_bit_flip_is_rejected(self) -> None:
        encoded = encode_packet(telemetry_packet())
        for index, mutation in enumerate(single_bit_mutations(encoded)):
            with self.subTest(index=index), self.assertRaises(ProtocolError):
                decode_packet(mutation)

    def test_every_truncation_and_bounded_extension_is_rejected(self) -> None:
        encoded = encode_packet(telemetry_packet())
        for mutation in byte_truncations(encoded) + byte_extensions(encoded):
            with self.subTest(length=len(mutation)), self.assertRaises(ProtocolError):
                decode_packet(mutation)

    def test_binary_corpus_is_rejected(self) -> None:
        payload = (CORPUS / "protocol/truncated.bin").read_bytes()
        with self.assertRaises(ProtocolError):
            decode_packet(payload)


class TelemetryRecordingParserHardeningTests(unittest.TestCase):
    def test_canonical_record_remains_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.jsonl"
            path.write_text(
                '{"packet_hex":"0001ff","received_at":10.5,"record_version":1}\n',
                encoding="utf-8",
            )
            self.assertEqual(list(iter_records(path)), [b"\x00\x01\xff"])

    def test_curated_recording_corpus_is_rejected(self) -> None:
        corpus = CORPUS / "telemetry-recording"
        for path in sorted(corpus.glob("*.jsonl")):
            with self.subTest(path=path.name), self.assertRaises(ValueError):
                list(iter_records(path))

    def test_replay_speed_rejects_boolean_nonfinite_and_nonpositive_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.jsonl"
            path.write_text("", encoding="utf-8")
            with self.assertRaises(TypeError):
                list(iter_records(path, speed=True))
            for speed in (
                0.0,
                -1.0,
                float("inf"),
                float("nan"),
                10**400,
            ):
                with self.subTest(speed=speed), self.assertRaises(ValueError):
                    list(iter_records(path, speed=speed))


class StructuredEventParserHardeningTests(unittest.TestCase):
    def test_link_event_rejects_each_missing_top_level_key(self) -> None:
        event = LinkEvent(
            session_id="parser-hardening",
            event_index=0,
            elapsed_ns=0,
            event_type=LinkEventType.PACKET_RECEIVED,
            packet_index=0,
            attributes={},
            schema_version=1,
        )
        for removed, document in mappings_without_each_key(event.to_dict()):
            with self.subTest(removed=removed), self.assertRaises(ValueError):
                LinkEvent.from_dict(document)

    def test_alarm_event_rejects_each_missing_top_level_key(self) -> None:
        event = AlarmEvent(
            session_id="parser-hardening",
            event_index=0,
            elapsed_ns=0,
            event_type=AlarmEventType.RUN_METADATA,
            attributes={
                "policy_fingerprint": "sha256:" + "0" * 64,
                "policy_name": "standard",
                "policy_reference": "builtin:standard",
                "policy_schema_version": 1,
            },
        )
        for removed, document in mappings_without_each_key(event.to_dict()):
            with self.subTest(removed=removed), self.assertRaises(ValueError):
                AlarmEvent.from_dict(document)

    def test_curated_link_and_alarm_event_corpora_are_rejected(self) -> None:
        for path in sorted((CORPUS / "link-events").glob("*.jsonl")):
            with self.subTest(path=path), self.assertRaises(ValueError):
                load_link_events(path)
        for path in sorted((CORPUS / "alarm-events").glob("*.jsonl")):
            with self.subTest(path=path), self.assertRaises(ValueError):
                load_alarm_events(path)


class TomlParserHardeningTests(unittest.TestCase):
    def test_mission_profile_corpus_and_truncations_are_rejected(self) -> None:
        malformed = CORPUS / "mission-profiles/unknown-key.toml"
        with self.assertRaises(ValueError):
            parse_mission_profile(malformed.read_text(encoding="utf-8"), source=str(malformed))

        valid = """\
schema_version = 1
name = "parser-hardening"

[link]
seed = 42
loss_rate = 0.125
duplicate_rate = 0.0
corrupt_rate = 0.0
latency_ms = 25
jitter_ms = 5
reorder_window = 2
"""
        for index, truncated in enumerate(bounded_text_truncations(valid.rstrip())):
            with self.subTest(index=index), self.assertRaises(ValueError):
                parse_mission_profile(truncated, source=f"<truncation-{index}>")

    def test_alarm_policy_corpus_and_truncations_are_rejected(self) -> None:
        malformed = CORPUS / "alarm-policies/unknown-key.toml"
        with self.assertRaises(ValueError):
            parse_alarm_policy(malformed.read_text(encoding="utf-8"), source=str(malformed))

        valid = """\
schema_version = 1
name = "parser-hardening"

[temperature]
warning_c = 50.0
critical_c = 60.0
hysteresis_c = 2.0

[battery]
critical_v = 7.0
hysteresis_v = 0.2

[mode]
alarm_on_safe = true

[sequence]
detect_gaps = true
"""
        for index, truncated in enumerate(bounded_text_truncations(valid.rstrip())):
            with self.subTest(index=index), self.assertRaises(ValueError):
                parse_alarm_policy(truncated, source=f"<truncation-{index}>")

    def test_equivalent_profile_documents_keep_one_effective_fingerprint(self) -> None:
        first = parse_mission_profile(
            """\
schema_version = 1
name = "first"

[link]
loss_rate = 0.25
latency_ms = 40
""",
        )
        second = parse_mission_profile(
            """\
name = "second"
schema_version = 1
description = "metadata does not affect the effective configuration"

[link]
latency_ms = 40
loss_rate = 0.250
""",
        )
        self.assertEqual(
            configuration_fingerprint(first.link_config),
            configuration_fingerprint(second.link_config),
        )

    def test_equivalent_alarm_policies_keep_one_effective_fingerprint(self) -> None:
        first = parse_alarm_policy(
            """\
schema_version = 1
name = "first"

[temperature]
warning_c = 50
critical_c = 60
hysteresis_c = 2

[battery]
critical_v = 7
hysteresis_v = 0.2

[mode]
alarm_on_safe = true

[sequence]
detect_gaps = true
""",
        )
        second = parse_alarm_policy(
            """\
name = "second"
schema_version = 1
description = "identity metadata is excluded from the effective policy"

[sequence]
detect_gaps = true

[mode]
alarm_on_safe = true

[battery]
hysteresis_v = 0.20
critical_v = 7.0

[temperature]
hysteresis_c = 2.0
critical_c = 60.0
warning_c = 50.0
""",
        )
        self.assertEqual(
            alarm_policy_fingerprint(first),
            alarm_policy_fingerprint(second),
        )


if __name__ == "__main__":
    unittest.main()

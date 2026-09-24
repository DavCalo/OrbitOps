from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.alarm_events import (  # noqa: E402
    AlarmEventType,
    load_alarm_events,
    validate_run_summary,
)
from orbitops.alarms import AlarmEngine  # noqa: E402
from orbitops.protocol import Mode, TelemetryPacket, encode_packet  # noqa: E402
from orbitops.receiver import (  # noqa: E402
    RecordingPathConflictError,
    format_packet,
    listen,
    process_packet,
)


def sample_packet(
    *,
    sequence: int = 1,
    temperature: int = 2500,
) -> TelemetryPacket:
    return TelemetryPacket(
        sequence=sequence,
        timestamp_ms=1,
        mode=Mode.NOMINAL,
        battery_mv=8100,
        bus_current_ma=400,
        temperature_centi_c=temperature,
        roll_centi_deg=100,
        pitch_centi_deg=-200,
        yaw_centi_deg=300,
    )


class FakeSocket:
    def __init__(self, datagram: bytes) -> None:
        self.datagram = datagram
        self.bound_to: tuple[str, int] | None = None
        self.calls = 0

    def __enter__(self) -> FakeSocket:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def bind(self, address: tuple[str, int]) -> None:
        self.bound_to = address

    def recvfrom(self, size: int) -> tuple[bytes, tuple[str, int]]:
        self.calls += 1
        if self.calls > 1:
            raise KeyboardInterrupt
        return self.datagram, ("127.0.0.1", 12345)


class ReceiverTests(unittest.TestCase):
    def _assert_recording_path_conflict(
        self,
        recording: Path,
        alarm_log: Path,
    ) -> None:
        with (
            patch("orbitops.receiver.socket.socket") as socket_factory,
            patch("orbitops.receiver.SessionRecorder") as session_recorder,
            patch("orbitops.receiver.AlarmEventRecorder") as alarm_recorder,
            self.assertRaisesRegex(RecordingPathConflictError, "same destination"),
        ):
            listen(
                "127.0.0.1",
                9000,
                recording,
                alarm_log_path=alarm_log,
            )
        socket_factory.assert_not_called()
        session_recorder.assert_not_called()
        alarm_recorder.assert_not_called()

    def test_listen_rejects_identical_recording_paths_before_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            shared = Path(directory) / "capture.jsonl"
            shared.write_text("preserve-me\n", encoding="utf-8")
            self._assert_recording_path_conflict(shared, shared)
            self.assertEqual(shared.read_text(encoding="utf-8"), "preserve-me\n")

    def test_listen_rejects_normalized_recording_path_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recording = Path(directory) / "capture.jsonl"
            alarm_log = Path(directory) / "nested" / ".." / "capture.jsonl"
            self._assert_recording_path_conflict(recording, alarm_log)

    def test_listen_rejects_symlink_recording_path_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recording = Path(directory) / "capture.jsonl"
            alarm_log = Path(directory) / "alarms.jsonl"
            try:
                alarm_log.symlink_to(recording.name)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlinks are unavailable: {exc}")
            self._assert_recording_path_conflict(recording, alarm_log)

    def test_listen_rejects_hard_link_recording_path_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recording = Path(directory) / "capture.jsonl"
            alarm_log = Path(directory) / "alarms.jsonl"
            recording.write_text("preserve-me\n", encoding="utf-8")
            try:
                alarm_log.hardlink_to(recording)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"hard links are unavailable: {exc}")
            self._assert_recording_path_conflict(recording, alarm_log)
            self.assertEqual(recording.read_text(encoding="utf-8"), "preserve-me\n")

    def test_format_packet(self) -> None:
        rendered = format_packet(sample_packet())
        self.assertIn("seq=00001", rendered)
        self.assertIn("mode=NOMINAL", rendered)
        self.assertIn("battery=8.100V", rendered)

    def test_process_packet_prints_alarm_only_on_transition(self) -> None:
        output = io.StringIO()
        engine = AlarmEngine()
        with contextlib.redirect_stdout(output):
            process_packet(encode_packet(sample_packet(temperature=6500)), engine)
            process_packet(
                encode_packet(sample_packet(sequence=2, temperature=6600)),
                engine,
            )

        rendered = output.getvalue()
        self.assertEqual(rendered.count("HIGH_TEMPERATURE"), 1)
        self.assertIn("!! CRITICAL HIGH_TEMPERATURE", rendered)

    def test_process_packet_forwards_transitions_to_alarm_recorder(self) -> None:
        recorder = Mock()
        process_packet(
            encode_packet(sample_packet(sequence=7, temperature=6500)),
            AlarmEngine(),
            recorder,
        )

        recorder.write_transitions.assert_called_once()
        sequence, transitions = recorder.write_transitions.call_args.args
        self.assertEqual(sequence, 7)
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0].code, "HIGH_TEMPERATURE")

    def test_listen_receives_and_records_telemetry_and_alarm_events(self) -> None:
        raw = encode_packet(sample_packet(temperature=6500))
        fake_socket = FakeSocket(raw)
        with tempfile.TemporaryDirectory() as directory:
            recording = Path(directory) / "capture.jsonl"
            alarm_log = Path(directory) / "alarms.jsonl"
            output = io.StringIO()
            with (
                patch("orbitops.receiver.socket.socket", return_value=fake_socket),
                contextlib.redirect_stdout(output),
                self.assertRaises(KeyboardInterrupt),
            ):
                listen(
                    "127.0.0.1",
                    9000,
                    recording,
                    alarm_log_path=alarm_log,
                )

            self.assertEqual(fake_socket.bound_to, ("127.0.0.1", 9000))
            self.assertIn("listening on udp://127.0.0.1:9000", output.getvalue())
            self.assertIn("Recording alarm lifecycle", output.getvalue())
            self.assertTrue(recording.read_text(encoding="utf-8").strip())

            events = load_alarm_events(alarm_log)
            self.assertEqual(events[0].event_type, AlarmEventType.RUN_METADATA)
            self.assertEqual(events[1].event_type, AlarmEventType.ALARM_RAISED)
            self.assertEqual(events[1].packet_sequence, 1)
            self.assertEqual(events[-1].event_type, AlarmEventType.RUN_SUMMARY)
            self.assertEqual(validate_run_summary(events).transitions_raised, 1)


if __name__ == "__main__":
    unittest.main()

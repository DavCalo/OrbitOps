"""UDP receiver and terminal presentation for OrbitOps."""

from __future__ import annotations

import contextlib
import socket
import time
from pathlib import Path

from .alarm_events import AlarmEventRecorder, AlarmRunMetadata
from .alarm_policies import AlarmPolicy
from .alarms import DEFAULT_ALARM_POLICY, AlarmEngine, format_alarm_transition
from .protocol import ProtocolError, TelemetryPacket, decode_packet
from .recorder import SessionRecorder


def format_packet(packet: TelemetryPacket) -> str:
    return (
        f"seq={packet.sequence:05d} "
        f"mode={packet.mode.name:<7} "
        f"battery={packet.battery_v:5.3f}V "
        f"current={packet.bus_current_ma:4d}mA "
        f"temp={packet.temperature_c:6.2f}C "
        f"att=({packet.roll_centi_deg / 100:6.2f},"
        f"{packet.pitch_centi_deg / 100:6.2f},"
        f"{packet.yaw_centi_deg / 100:6.2f})deg"
    )


def process_packet(
    raw: bytes,
    engine: AlarmEngine,
    alarm_recorder: AlarmEventRecorder | None = None,
) -> None:
    packet = decode_packet(raw)
    print(format_packet(packet))
    transitions = engine.evaluate(packet)
    if alarm_recorder is not None:
        alarm_recorder.write_transitions(packet.sequence, transitions)
    for transition in transitions:
        print(format_alarm_transition(transition))


def listen(
    host: str,
    port: int,
    record_path: Path | None = None,
    alarm_policy: AlarmPolicy = DEFAULT_ALARM_POLICY,
    alarm_log_path: Path | None = None,
    alarm_policy_reference: str = "builtin:standard",
) -> None:
    engine = AlarmEngine(alarm_policy)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((host, port))
        print(
            f"OrbitOps ground station listening on udp://{host}:{port}",
            flush=True,
        )

        with contextlib.ExitStack() as stack:
            recorder = (
                stack.enter_context(SessionRecorder(record_path))
                if record_path is not None
                else None
            )
            alarm_recorder = (
                stack.enter_context(
                    AlarmEventRecorder(
                        alarm_log_path,
                        AlarmRunMetadata.from_policy(
                            alarm_policy,
                            reference=alarm_policy_reference,
                        ),
                    )
                )
                if alarm_log_path is not None
                else None
            )

            if record_path is not None:
                print(f"Recording session to {record_path}", flush=True)
            if alarm_log_path is not None:
                print(
                    f"Recording alarm lifecycle to {alarm_log_path} policy={alarm_policy.name}",
                    flush=True,
                )

            while True:
                raw, sender = sock.recvfrom(4096)
                received_at = time.time()
                if recorder is not None:
                    recorder.write(raw, received_at)
                try:
                    process_packet(raw, engine, alarm_recorder)
                except ProtocolError as exc:
                    print(
                        f"REJECT from {sender[0]}:{sender[1]}: {exc}",
                        flush=True,
                    )

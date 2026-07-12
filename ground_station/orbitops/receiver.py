"""UDP receiver and terminal presentation for OrbitOps."""

from __future__ import annotations

import contextlib
import socket
import time
from pathlib import Path

from .alarms import AlarmEngine, format_alarm_transition
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


def process_packet(raw: bytes, engine: AlarmEngine) -> None:
    packet = decode_packet(raw)
    print(format_packet(packet))
    for transition in engine.evaluate(packet):
        print(format_alarm_transition(transition))


def listen(host: str, port: int, record_path: Path | None = None) -> None:
    engine = AlarmEngine()
    recorder_context = (
        SessionRecorder(record_path) if record_path is not None else contextlib.nullcontext()
    )

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock, recorder_context as recorder:
        sock.bind((host, port))
        print(f"OrbitOps ground station listening on udp://{host}:{port}")
        if record_path:
            print(f"Recording session to {record_path}")

        while True:
            raw, sender = sock.recvfrom(4096)
            received_at = time.time()
            if isinstance(recorder, SessionRecorder):
                recorder.write(raw, received_at)
            try:
                process_packet(raw, engine)
            except ProtocolError as exc:
                print(f"REJECT from {sender[0]}:{sender[1]}: {exc}")

"""Simple alarm and sequence-gap evaluation for OrbitOps telemetry."""

from __future__ import annotations

from dataclasses import dataclass

from .protocol import Mode, TelemetryPacket


@dataclass(frozen=True)
class Alarm:
    severity: str
    code: str
    message: str


class AlarmEngine:
    def __init__(self) -> None:
        self._last_sequence: int | None = None

    def evaluate(self, packet: TelemetryPacket) -> list[Alarm]:
        alarms: list[Alarm] = []

        if self._last_sequence is not None:
            expected = self._last_sequence + 1
            if packet.sequence != expected:
                alarms.append(
                    Alarm(
                        severity="warning",
                        code="SEQUENCE_GAP",
                        message=f"expected sequence {expected}, received {packet.sequence}",
                    )
                )
        self._last_sequence = packet.sequence

        if packet.temperature_c >= 60.0:
            alarms.append(
                Alarm(
                    severity="critical",
                    code="HIGH_TEMPERATURE",
                    message=f"temperature is {packet.temperature_c:.2f} °C",
                )
            )
        elif packet.temperature_c >= 50.0:
            alarms.append(
                Alarm(
                    severity="warning",
                    code="ELEVATED_TEMPERATURE",
                    message=f"temperature is {packet.temperature_c:.2f} °C",
                )
            )

        if packet.battery_v <= 7.0:
            alarms.append(
                Alarm(
                    severity="critical",
                    code="LOW_BATTERY",
                    message=f"battery voltage is {packet.battery_v:.3f} V",
                )
            )

        if packet.mode is Mode.SAFE:
            alarms.append(
                Alarm(
                    severity="warning",
                    code="SAFE_MODE",
                    message="spacecraft reports SAFE mode",
                )
            )

        return alarms

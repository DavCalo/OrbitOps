"""Deterministic link-emulator components for OrbitOps."""

from .config import LinkConfig
from .decisions import Delivery, PacketOutcome
from .events import (
    LINK_EVENT_SCHEMA_VERSION,
    JsonlEventRecorder,
    LinkEvent,
    LinkEventType,
    load_link_events,
)
from .impairments import ImpairmentEngine, flip_bit
from .runtime import LinkRuntime
from .scheduler import DatagramScheduler, ScheduledDatagram
from .statistics import LinkStatistics, statistics_from_events, validate_run_summary

__all__ = [
    "LINK_EVENT_SCHEMA_VERSION",
    "DatagramScheduler",
    "Delivery",
    "ImpairmentEngine",
    "JsonlEventRecorder",
    "LinkConfig",
    "LinkEvent",
    "LinkEventType",
    "LinkRuntime",
    "LinkStatistics",
    "PacketOutcome",
    "ScheduledDatagram",
    "flip_bit",
    "load_link_events",
    "statistics_from_events",
    "validate_run_summary",
]

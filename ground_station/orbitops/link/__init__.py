"""Deterministic link-emulator components for OrbitOps."""

from .config import LinkConfig
from .decisions import Delivery, PacketOutcome
from .events import (
    LINK_EVENT_SCHEMA_VERSION,
    JsonlEventRecorder,
    LinkEvent,
    LinkEventType,
    LinkRunMetadata,
    load_link_events,
)
from .fingerprint import (
    EFFECTIVE_CONFIG_SCHEMA_VERSION,
    canonical_effective_config,
    configuration_fingerprint,
)
from .impairments import ImpairmentEngine, flip_bit
from .runtime import LinkRuntime
from .scheduler import DatagramScheduler, ScheduledDatagram
from .statistics import (
    LinkStatistics,
    run_metadata_from_events,
    statistics_from_events,
    validate_run_summary,
)

__all__ = [
    "EFFECTIVE_CONFIG_SCHEMA_VERSION",
    "LINK_EVENT_SCHEMA_VERSION",
    "DatagramScheduler",
    "Delivery",
    "ImpairmentEngine",
    "JsonlEventRecorder",
    "LinkConfig",
    "LinkEvent",
    "LinkEventType",
    "LinkRunMetadata",
    "LinkRuntime",
    "LinkStatistics",
    "PacketOutcome",
    "ScheduledDatagram",
    "canonical_effective_config",
    "configuration_fingerprint",
    "flip_bit",
    "load_link_events",
    "run_metadata_from_events",
    "statistics_from_events",
    "validate_run_summary",
]

"""Deterministic scheduling for link-emulator deliveries."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from .decisions import PacketOutcome

_NANOSECONDS_PER_MILLISECOND = 1_000_000


@dataclass(order=True, frozen=True, slots=True)
class ScheduledDatagram:
    """One datagram waiting for both its time and packet-hold constraints."""

    due_at_ns: int
    packet_index: int
    copy_index: int
    release_after_packet: int
    payload: bytes = field(compare=False)
    corrupted_bit: int | None = field(compare=False)


class DatagramScheduler:
    """Schedule immutable packet outcomes using a caller-provided monotonic clock.

    The scheduler does not read wall-clock time. Callers supply ``received_at_ns``
    and ``now_ns``, which keeps ordering deterministic in unit tests and avoids
    coupling the pure scheduling semantics to a particular runtime loop.
    """

    __slots__ = ("_highest_packet_index", "_pending", "_release_holds")

    def __init__(self) -> None:
        self._pending: list[ScheduledDatagram] = []
        self._highest_packet_index = -1
        self._release_holds = False

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def highest_packet_index(self) -> int:
        return self._highest_packet_index

    def enqueue(self, outcome: PacketOutcome, received_at_ns: int) -> None:
        """Add one outcome and advance the observed packet stream.

        Dropped packets still advance the packet index. That behavior is required
        because a previously held delivery is released after a bounded number of
        *received* packets, not forwarded packets.
        """

        if isinstance(received_at_ns, bool) or not isinstance(received_at_ns, int):
            raise TypeError("received_at_ns must be an integer")
        if received_at_ns < 0:
            raise ValueError("received_at_ns must be non-negative")
        if outcome.packet_index <= self._highest_packet_index:
            raise ValueError("packet outcomes must be enqueued in strictly increasing order")

        self._highest_packet_index = outcome.packet_index
        for delivery in outcome.deliveries:
            heapq.heappush(
                self._pending,
                ScheduledDatagram(
                    due_at_ns=received_at_ns + delivery.delay_ms * _NANOSECONDS_PER_MILLISECOND,
                    packet_index=outcome.packet_index,
                    copy_index=delivery.copy_index,
                    release_after_packet=outcome.packet_index + delivery.hold_packets,
                    payload=delivery.payload,
                    corrupted_bit=delivery.corrupted_bit,
                ),
            )

    def release_holds(self) -> None:
        """Allow all queued deliveries to drain when an input stream ends."""

        self._release_holds = True

    def pop_ready(self, now_ns: int) -> tuple[ScheduledDatagram, ...]:
        """Remove all deliveries whose delay and hold constraints are satisfied."""

        if isinstance(now_ns, bool) or not isinstance(now_ns, int):
            raise TypeError("now_ns must be an integer")
        if now_ns < 0:
            raise ValueError("now_ns must be non-negative")

        blocked: list[ScheduledDatagram] = []
        ready: list[ScheduledDatagram] = []
        while self._pending and self._pending[0].due_at_ns <= now_ns:
            item = heapq.heappop(self._pending)
            released = (
                self._release_holds or item.release_after_packet <= self._highest_packet_index
            )
            if released:
                ready.append(item)
            else:
                blocked.append(item)

        for item in blocked:
            heapq.heappush(self._pending, item)
        return tuple(ready)

    def next_deadline_ns(self) -> int | None:
        """Return the earliest due time among packet-hold-eligible deliveries."""

        deadlines = (
            item.due_at_ns
            for item in self._pending
            if self._release_holds or item.release_after_packet <= self._highest_packet_index
        )
        return min(deadlines, default=None)

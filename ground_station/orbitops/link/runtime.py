"""UDP proxy runtime for the deterministic OrbitOps link emulator."""

from __future__ import annotations

import contextlib
import math
import signal
import socket
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from types import FrameType
from typing import Any

from .config import LinkConfig
from .decisions import PacketOutcome
from .events import EventSink, LinkEventType
from .impairments import ImpairmentEngine
from .scheduler import DatagramScheduler, ScheduledDatagram
from .statistics import LinkEventStream, LinkStatistics

Address = tuple[str, int]
Clock = Callable[[], int]

_MAX_DATAGRAM_SIZE = 65_535
_DEFAULT_POLL_INTERVAL_S = 0.05


@contextlib.contextmanager
def _temporary_stop_handlers(stop_event: threading.Event) -> Iterator[None]:
    """Translate SIGINT and SIGTERM into a cooperative stop request on main."""

    if threading.current_thread() is not threading.main_thread():
        yield
        return

    previous: dict[signal.Signals, Any] = {}

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        stop_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, request_stop)
    try:
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


class LinkRuntime:
    """Forward UDP datagrams through deterministic impairments and scheduling.

    ``open`` binds the receiving endpoint so callers can discover an ephemeral
    port before starting the loop. ``run`` owns the loop lifetime and always
    closes both sockets before returning or propagating an exception.
    """

    __slots__ = (
        "_clock",
        "_config",
        "_event_sink",
        "_event_stream",
        "_forward_address",
        "_highest_forwarded_packet_index",
        "_input_socket",
        "_listen_address",
        "_output_socket",
        "_poll_interval_s",
        "_reordered_packets",
        "_scheduler",
        "_session_id",
        "engine",
    )

    def __init__(
        self,
        listen_address: Address,
        forward_address: Address,
        config: LinkConfig,
        *,
        clock: Clock = time.monotonic_ns,
        poll_interval_s: float = _DEFAULT_POLL_INTERVAL_S,
        event_sink: EventSink | None = None,
        session_id: str | None = None,
    ) -> None:
        if isinstance(poll_interval_s, bool) or not math.isfinite(poll_interval_s):
            raise ValueError("poll_interval_s must be a finite positive number")
        if not 0.0 < poll_interval_s <= 1.0:
            raise ValueError("poll_interval_s must be between 0.0 and 1.0")
        if session_id is not None and (not isinstance(session_id, str) or not session_id.strip()):
            raise ValueError("session_id must be a non-empty string")
        self._listen_address = listen_address
        self._config = config
        self._forward_address = forward_address
        self._clock = clock
        self._poll_interval_s = poll_interval_s
        self._event_sink = event_sink
        self._session_id = session_id
        self.engine = ImpairmentEngine(config)
        self._scheduler = DatagramScheduler()
        self._input_socket: socket.socket | None = None
        self._output_socket: socket.socket | None = None
        self._event_stream: LinkEventStream | None = None
        self._highest_forwarded_packet_index = -1
        self._reordered_packets: set[int] = set()

    @property
    def is_open(self) -> bool:
        return self._input_socket is not None and self._output_socket is not None

    @property
    def bound_address(self) -> Address:
        if self._input_socket is None:
            raise RuntimeError("link runtime is not open")
        host, port = self._input_socket.getsockname()[:2]
        return str(host), int(port)

    @property
    def pending_count(self) -> int:
        return self._scheduler.pending_count

    @property
    def statistics(self) -> LinkStatistics:
        if self._event_stream is None:
            return LinkStatistics()
        return self._event_stream.statistics

    def open(self) -> None:
        if self.is_open:
            raise RuntimeError("link runtime is already open")

        input_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        output_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            input_socket.bind(self._listen_address)
        except BaseException:
            input_socket.close()
            output_socket.close()
            raise

        self.engine = ImpairmentEngine(self._config)
        self._scheduler = DatagramScheduler()
        self._event_stream = None
        self._highest_forwarded_packet_index = -1
        self._reordered_packets.clear()
        self._input_socket = input_socket
        self._output_socket = output_socket

    def close(self) -> None:
        input_socket, self._input_socket = self._input_socket, None
        output_socket, self._output_socket = self._output_socket, None
        if input_socket is not None:
            input_socket.close()
        if output_socket is not None:
            output_socket.close()

    def _emit_outcome(self, raw: bytes, outcome: PacketOutcome, now_ns: int) -> None:
        if self._event_stream is None:
            raise RuntimeError("event stream is not initialized")

        packet_index = outcome.packet_index
        self._event_stream.emit(
            LinkEventType.PACKET_RECEIVED,
            now_ns,
            packet_index=packet_index,
            attributes={"payload_bytes": len(raw)},
        )
        if outcome.dropped:
            self._event_stream.emit(
                LinkEventType.PACKET_DROPPED,
                now_ns,
                packet_index=packet_index,
                attributes={"payload_bytes": len(raw)},
            )
            return

        first = outcome.deliveries[0]
        if outcome.duplicated:
            self._event_stream.emit(
                LinkEventType.PACKET_DUPLICATED,
                now_ns,
                packet_index=packet_index,
                attributes={"copies": len(outcome.deliveries)},
            )
        if first.corrupted_bit is not None:
            self._event_stream.emit(
                LinkEventType.PACKET_CORRUPTED,
                now_ns,
                packet_index=packet_index,
                attributes={"corrupted_bit": first.corrupted_bit},
            )
        if first.delay_ms > 0:
            self._event_stream.emit(
                LinkEventType.PACKET_DELAYED,
                now_ns,
                packet_index=packet_index,
                attributes={"delay_ms": first.delay_ms},
            )

        for delivery in outcome.deliveries:
            self._event_stream.emit(
                LinkEventType.DELIVERY_SCHEDULED,
                now_ns,
                packet_index=packet_index,
                attributes={
                    "copy_index": delivery.copy_index,
                    "corrupted_bit": delivery.corrupted_bit,
                    "delay_ms": delivery.delay_ms,
                    "hold_packets": delivery.hold_packets,
                    "payload_bytes": len(delivery.payload),
                },
            )

    def _emit_forwarded(self, item: ScheduledDatagram, now_ns: int) -> None:
        if self._event_stream is None:
            raise RuntimeError("event stream is not initialized")

        if (
            item.packet_index < self._highest_forwarded_packet_index
            and item.packet_index not in self._reordered_packets
        ):
            self._reordered_packets.add(item.packet_index)
            self._event_stream.emit(
                LinkEventType.PACKET_REORDERED,
                now_ns,
                packet_index=item.packet_index,
                attributes={
                    "overtaken_by_packet_index": self._highest_forwarded_packet_index,
                    "release_after_packet": item.release_after_packet,
                },
            )
        self._highest_forwarded_packet_index = max(
            self._highest_forwarded_packet_index,
            item.packet_index,
        )
        self._event_stream.emit(
            LinkEventType.PACKET_FORWARDED,
            now_ns,
            packet_index=item.packet_index,
            attributes={
                "copy_index": item.copy_index,
                "corrupted_bit": item.corrupted_bit,
                "payload_bytes": len(item.payload),
            },
        )

    def _send_ready(self, now_ns: int) -> int:
        if self._output_socket is None:
            raise RuntimeError("link runtime is not open")

        sent = 0
        for item in self._scheduler.pop_ready(now_ns):
            transmitted = self._output_socket.sendto(item.payload, self._forward_address)
            if transmitted != len(item.payload):
                raise RuntimeError("failed to forward complete UDP datagram")
            self._emit_forwarded(item, now_ns)
            sent += 1
        return sent

    def _receive_timeout(self, now_ns: int) -> float:
        deadline = self._scheduler.next_deadline_ns()
        if deadline is None:
            return self._poll_interval_s
        remaining_s = max(0, deadline - now_ns) / 1_000_000_000
        return min(self._poll_interval_s, remaining_s)

    def run(
        self,
        *,
        stop_event: threading.Event | None = None,
        ready_event: threading.Event | None = None,
        max_packets: int | None = None,
    ) -> None:
        """Run until stopped, or until ``max_packets`` are received and drained."""

        if isinstance(max_packets, bool):
            raise TypeError("max_packets must be an integer or None")
        if max_packets is not None and max_packets <= 0:
            raise ValueError("max_packets must be positive")
        if not self.is_open:
            raise RuntimeError("link runtime must be opened before run")
        if self._input_socket is None:
            raise AssertionError("input socket missing after open")

        stop = stop_event or threading.Event()
        received_packets = 0
        draining = False
        start_ns = self._clock()
        session_id = self._session_id or uuid.uuid4().hex
        self._event_stream = LinkEventStream(session_id, start_ns, self._event_sink)
        if ready_event is not None:
            ready_event.set()

        try:
            with _temporary_stop_handlers(stop):
                while not stop.is_set():
                    now_ns = self._clock()
                    self._send_ready(now_ns)
                    if draining and self._scheduler.pending_count == 0:
                        break

                    if draining:
                        deadline = self._scheduler.next_deadline_ns()
                        if deadline is None:
                            break
                        sleep_s = min(
                            self._poll_interval_s,
                            max(0, deadline - self._clock()) / 1_000_000_000,
                        )
                        if sleep_s > 0:
                            stop.wait(sleep_s)
                        continue

                    self._input_socket.settimeout(self._receive_timeout(now_ns))
                    try:
                        raw, _sender = self._input_socket.recvfrom(_MAX_DATAGRAM_SIZE)
                    except TimeoutError:
                        continue

                    received_at_ns = self._clock()
                    outcome = self.engine.process(raw)
                    self._emit_outcome(raw, outcome, received_at_ns)
                    self._scheduler.enqueue(outcome, received_at_ns)
                    received_packets += 1
                    if max_packets is not None and received_packets >= max_packets:
                        self._scheduler.release_holds()
                        draining = True
        finally:
            try:
                if self._event_stream is not None:
                    self._event_stream.emit_summary(self._clock())
            finally:
                self.close()

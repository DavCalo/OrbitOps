from __future__ import annotations

import unittest

from orbitops.link.decisions import Delivery, PacketOutcome
from orbitops.link.scheduler import DatagramScheduler


class DatagramSchedulerTests(unittest.TestCase):
    def delivery(
        self,
        payload: bytes,
        *,
        copy_index: int = 0,
        delay_ms: int = 0,
        hold_packets: int = 0,
    ) -> Delivery:
        return Delivery(
            payload=payload,
            copy_index=copy_index,
            delay_ms=delay_ms,
            hold_packets=hold_packets,
            corrupted_bit=None,
        )

    def outcome(self, index: int, *deliveries: Delivery) -> PacketOutcome:
        return PacketOutcome(packet_index=index, dropped=not deliveries, deliveries=deliveries)

    def test_delay_and_stable_tie_order(self) -> None:
        scheduler = DatagramScheduler()
        scheduler.enqueue(
            self.outcome(
                0,
                self.delivery(b"first", copy_index=0, delay_ms=10),
                self.delivery(b"duplicate", copy_index=1, delay_ms=10),
            ),
            received_at_ns=5,
        )

        self.assertEqual(scheduler.pop_ready(9_999_999), ())
        ready = scheduler.pop_ready(10_000_005)
        self.assertEqual([item.payload for item in ready], [b"first", b"duplicate"])
        self.assertEqual(scheduler.pending_count, 0)

    def test_packet_hold_allows_newer_datagram_to_overtake(self) -> None:
        scheduler = DatagramScheduler()
        scheduler.enqueue(
            self.outcome(0, self.delivery(b"held", hold_packets=2)),
            received_at_ns=0,
        )
        scheduler.enqueue(self.outcome(1, self.delivery(b"newer")), received_at_ns=1)

        self.assertEqual([item.payload for item in scheduler.pop_ready(1)], [b"newer"])
        scheduler.enqueue(self.outcome(2), received_at_ns=2)
        self.assertEqual([item.payload for item in scheduler.pop_ready(2)], [b"held"])

    def test_dropped_packets_advance_hold_release(self) -> None:
        scheduler = DatagramScheduler()
        scheduler.enqueue(
            self.outcome(0, self.delivery(b"held", hold_packets=1)),
            received_at_ns=0,
        )
        scheduler.enqueue(self.outcome(1), received_at_ns=1)
        self.assertEqual([item.payload for item in scheduler.pop_ready(1)], [b"held"])

    def test_release_holds_drains_end_of_stream(self) -> None:
        scheduler = DatagramScheduler()
        scheduler.enqueue(
            self.outcome(0, self.delivery(b"tail", delay_ms=2, hold_packets=10)),
            received_at_ns=10,
        )
        self.assertIsNone(scheduler.next_deadline_ns())
        scheduler.release_holds()
        self.assertEqual(scheduler.next_deadline_ns(), 2_000_010)
        self.assertEqual(scheduler.pop_ready(2_000_009), ())
        self.assertEqual([item.payload for item in scheduler.pop_ready(2_000_010)], [b"tail"])

    def test_rejects_invalid_times_and_out_of_order_outcomes(self) -> None:
        scheduler = DatagramScheduler()
        with self.assertRaises(TypeError):
            scheduler.enqueue(self.outcome(0), received_at_ns=True)
        with self.assertRaises(ValueError):
            scheduler.enqueue(self.outcome(0), received_at_ns=-1)

        scheduler.enqueue(self.outcome(0), received_at_ns=0)
        with self.assertRaises(ValueError):
            scheduler.enqueue(self.outcome(0), received_at_ns=0)
        with self.assertRaises(TypeError):
            scheduler.pop_ready(True)
        with self.assertRaises(ValueError):
            scheduler.pop_ready(-1)


if __name__ == "__main__":
    unittest.main()

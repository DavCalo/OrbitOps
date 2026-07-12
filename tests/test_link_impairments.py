from __future__ import annotations

import math
import sys
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.link import ImpairmentEngine, LinkConfig, flip_bit  # noqa: E402
from orbitops.link.decisions import SplitMix64, probability_hit, scale_u64  # noqa: E402


class LinkConfigTests(unittest.TestCase):
    def test_defaults_are_noop(self) -> None:
        self.assertEqual(LinkConfig(), LinkConfig(seed=0))

    def test_invalid_rates_are_rejected(self) -> None:
        for value in (-0.01, 1.01, math.inf, -math.inf, math.nan):
            with self.subTest(value=value), self.assertRaises(ValueError):
                LinkConfig(loss_rate=value)
        with self.assertRaises(TypeError):
            LinkConfig(loss_rate=cast(Any, True))

    def test_invalid_integer_configuration_is_rejected(self) -> None:
        invalid_factories: list[Callable[[], LinkConfig]] = [
            lambda: LinkConfig(seed=-1),
            lambda: LinkConfig(seed=1 << 64),
            lambda: LinkConfig(latency_ms=-1),
            lambda: LinkConfig(jitter_ms=-1),
            lambda: LinkConfig(reorder_window=-1),
            lambda: LinkConfig(reorder_window=65_536),
        ]
        for factory in invalid_factories:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()
        with self.assertRaises(TypeError):
            LinkConfig(latency_ms=cast(Any, 1.5))


class PrimitiveTests(unittest.TestCase):
    def test_splitmix64_golden_sequence(self) -> None:
        generator = SplitMix64(42)
        self.assertEqual(
            [generator.next_u64() for _ in range(4)],
            [
                13_679_457_532_755_275_413,
                2_949_826_092_126_892_291,
                5_139_283_748_462_763_858,
                6_349_198_060_258_255_764,
            ],
        )

    def test_probability_boundaries(self) -> None:
        self.assertFalse(probability_hit(0, 0.0))
        self.assertTrue(probability_hit((1 << 64) - 1, 1.0))

    def test_scale_u64_range_and_validation(self) -> None:
        self.assertEqual(scale_u64(0, 5), 0)
        self.assertEqual(scale_u64((1 << 64) - 1, 5), 4)
        with self.assertRaises(ValueError):
            scale_u64(0, 0)

    def test_flip_bit_changes_exactly_one_bit(self) -> None:
        before = bytes.fromhex("00ff")
        after = flip_bit(before, 8)
        self.assertEqual(after, bytes.fromhex("00fe"))
        difference = int.from_bytes(before, "big") ^ int.from_bytes(after, "big")
        self.assertEqual(difference.bit_count(), 1)
        with self.assertRaises(ValueError):
            flip_bit(before, 16)


class ImpairmentEngineTests(unittest.TestCase):
    def test_default_configuration_is_exact_pass_through(self) -> None:
        engine = ImpairmentEngine(LinkConfig())
        payload = b"orbitops"
        outcome = engine.process(payload)
        self.assertFalse(outcome.dropped)
        self.assertFalse(outcome.duplicated)
        self.assertEqual(outcome.deliveries[0].payload, payload)
        self.assertEqual(outcome.deliveries[0].delay_ms, 0)
        self.assertEqual(outcome.deliveries[0].hold_packets, 0)
        self.assertIsNone(outcome.deliveries[0].corrupted_bit)

    def test_always_loss_drops_without_delivery(self) -> None:
        outcome = ImpairmentEngine(LinkConfig(loss_rate=1.0)).process(b"data")
        self.assertTrue(outcome.dropped)
        self.assertEqual(outcome.deliveries, ())

    def test_always_duplicate_emits_two_identical_copies(self) -> None:
        outcome = ImpairmentEngine(LinkConfig(duplicate_rate=1.0)).process(b"data")
        self.assertTrue(outcome.duplicated)
        self.assertEqual([item.copy_index for item in outcome.deliveries], [0, 1])
        self.assertEqual(outcome.deliveries[0].payload, outcome.deliveries[1].payload)

    def test_corruption_is_reproducible_and_flips_one_bit(self) -> None:
        payload = b"abcdef"
        first = ImpairmentEngine(LinkConfig(seed=9, corrupt_rate=1.0)).process(payload)
        second = ImpairmentEngine(LinkConfig(seed=9, corrupt_rate=1.0)).process(payload)
        self.assertEqual(first, second)
        delivery = first.deliveries[0]
        self.assertIsNotNone(delivery.corrupted_bit)
        difference = int.from_bytes(payload, "big") ^ int.from_bytes(delivery.payload, "big")
        self.assertEqual(difference.bit_count(), 1)

    def test_empty_payload_cannot_apply_corruption(self) -> None:
        outcome = ImpairmentEngine(LinkConfig(corrupt_rate=1.0)).process(b"")
        self.assertEqual(outcome.deliveries[0].payload, b"")
        self.assertIsNone(outcome.deliveries[0].corrupted_bit)

    def test_delay_and_reordering_stay_in_bounds(self) -> None:
        engine = ImpairmentEngine(LinkConfig(seed=8, latency_ms=20, jitter_ms=7, reorder_window=3))
        for _ in range(200):
            delivery = engine.process(b"x").deliveries[0]
            self.assertGreaterEqual(delivery.delay_ms, 13)
            self.assertLessEqual(delivery.delay_ms, 27)
            self.assertGreaterEqual(delivery.hold_packets, 0)
            self.assertLessEqual(delivery.hold_packets, 3)

    def test_negative_effective_delay_is_clamped_to_zero(self) -> None:
        engine = ImpairmentEngine(LinkConfig(seed=1, latency_ms=0, jitter_ms=100))
        for _ in range(50):
            self.assertGreaterEqual(engine.process(b"x").deliveries[0].delay_ms, 0)

    def test_same_input_stream_produces_same_outcomes(self) -> None:
        config = LinkConfig(
            seed=2026,
            loss_rate=0.2,
            duplicate_rate=0.3,
            corrupt_rate=0.4,
            latency_ms=80,
            jitter_ms=20,
            reorder_window=4,
        )
        packets = [bytes([index]) * (index + 1) for index in range(20)]
        engine_a = ImpairmentEngine(config)
        engine_b = ImpairmentEngine(config)
        self.assertEqual(
            [engine_a.process(packet) for packet in packets],
            [engine_b.process(packet) for packet in packets],
        )

    def test_golden_combined_decisions(self) -> None:
        config = LinkConfig(
            seed=42,
            loss_rate=0.25,
            duplicate_rate=0.5,
            corrupt_rate=0.5,
            latency_ms=100,
            jitter_ms=15,
            reorder_window=3,
        )
        engine = ImpairmentEngine(config)
        outcomes = [engine.process(bytes([index, 0xA5])) for index in range(6)]
        signature = [
            (
                outcome.packet_index,
                outcome.dropped,
                len(outcome.deliveries),
                None if not outcome.deliveries else outcome.deliveries[0].delay_ms,
                None if not outcome.deliveries else outcome.deliveries[0].hold_packets,
                None if not outcome.deliveries else outcome.deliveries[0].corrupted_bit,
                None if not outcome.deliveries else outcome.deliveries[0].payload.hex(),
            )
            for outcome in outcomes
        ]
        self.assertEqual(
            signature,
            [
                (0, False, 2, 95, 0, 13, "0085"),
                (1, True, 0, None, None, None, None),
                (2, False, 1, 91, 0, None, "02a5"),
                (3, True, 0, None, None, None, None),
                (4, True, 0, None, None, None, None),
                (5, False, 1, 109, 2, None, "05a5"),
            ],
        )

    def test_packet_index_advances_and_payload_type_is_strict(self) -> None:
        engine = ImpairmentEngine(LinkConfig())
        self.assertEqual(engine.packet_index, 0)
        self.assertEqual(engine.process(b"one").packet_index, 0)
        self.assertEqual(engine.packet_index, 1)
        with self.assertRaises(TypeError):
            engine.process(cast(Any, bytearray(b"two")))


if __name__ == "__main__":
    unittest.main()

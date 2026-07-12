from __future__ import annotations

import signal
import socket
import threading
import unittest
from unittest import mock

from orbitops.link import LinkConfig
from orbitops.link.runtime import LinkRuntime, _temporary_stop_handlers


class LinkRuntimeTests(unittest.TestCase):
    def receiver(self) -> socket.socket:
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(2.0)
        return receiver

    def run_one(self, config: LinkConfig, payload: bytes) -> tuple[list[bytes], tuple[str, int]]:
        with self.receiver() as receiver:
            target = receiver.getsockname()
            runtime = LinkRuntime(("127.0.0.1", 0), target, config)
            runtime.open()
            listen_address = runtime.bound_address
            thread = threading.Thread(target=runtime.run, kwargs={"max_packets": 1})
            thread.start()

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                sender.sendto(payload, listen_address)

            expected = 2 if config.duplicate_rate == 1.0 and config.loss_rate == 0.0 else 1
            received: list[bytes] = []
            if config.loss_rate == 0.0:
                for _ in range(expected):
                    received.append(receiver.recvfrom(4096)[0])
            thread.join(timeout=2.0)
            self.assertFalse(thread.is_alive())
            self.assertFalse(runtime.is_open)
            return received, listen_address

    def test_nominal_runtime_preserves_datagram(self) -> None:
        received, _address = self.run_one(LinkConfig(), b"orbitops")
        self.assertEqual(received, [b"orbitops"])

    def test_duplicate_and_corruption_are_forwarded(self) -> None:
        received, _address = self.run_one(
            LinkConfig(seed=7, duplicate_rate=1.0, corrupt_rate=1.0),
            b"payload",
        )
        self.assertEqual(len(received), 2)
        self.assertEqual(received[0], received[1])
        self.assertNotEqual(received[0], b"payload")

    def test_bound_port_is_reusable_after_runtime_closes(self) -> None:
        _received, address = self.run_one(LinkConfig(), b"one")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as rebound:
            rebound.bind(address)

    def test_stop_event_closes_idle_runtime(self) -> None:
        with self.receiver() as receiver:
            runtime = LinkRuntime(
                ("127.0.0.1", 0),
                receiver.getsockname(),
                LinkConfig(),
                poll_interval_s=0.01,
            )
            runtime.open()
            stop = threading.Event()
            thread = threading.Thread(target=runtime.run, kwargs={"stop_event": stop})
            thread.start()
            stop.set()
            thread.join(timeout=1.0)
            self.assertFalse(thread.is_alive())
            self.assertFalse(runtime.is_open)

    def test_signal_handlers_request_stop_and_are_restored(self) -> None:
        stop = threading.Event()
        with (
            mock.patch("orbitops.link.runtime.signal.getsignal", return_value=signal.SIG_DFL),
            mock.patch("orbitops.link.runtime.signal.signal") as install,
            _temporary_stop_handlers(stop),
        ):
            first_handler = install.call_args_list[0].args[1]
            first_handler(signal.SIGINT, None)
            self.assertTrue(stop.is_set())

        self.assertEqual(install.call_count, 4)

    def test_reopening_resets_deterministic_state(self) -> None:
        with self.receiver() as receiver:
            runtime = LinkRuntime(("127.0.0.1", 0), receiver.getsockname(), LinkConfig(seed=11))
            for payload in (b"first", b"second"):
                runtime.open()
                address = runtime.bound_address
                thread = threading.Thread(target=runtime.run, kwargs={"max_packets": 1})
                thread.start()
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    sender.sendto(payload, address)
                self.assertEqual(receiver.recvfrom(4096)[0], payload)
                thread.join(timeout=1.0)
                self.assertFalse(thread.is_alive())

    def test_open_and_run_validation(self) -> None:
        with self.assertRaises(ValueError):
            LinkRuntime(("127.0.0.1", 0), ("127.0.0.1", 9), LinkConfig(), poll_interval_s=0)
        with self.assertRaises(ValueError):
            LinkRuntime(
                ("127.0.0.1", 0),
                ("127.0.0.1", 9),
                LinkConfig(),
                poll_interval_s=float("nan"),
            )

        runtime = LinkRuntime(("127.0.0.1", 0), ("127.0.0.1", 9), LinkConfig())
        with self.assertRaises(RuntimeError):
            _ = runtime.bound_address
        with self.assertRaises(RuntimeError):
            runtime.run(max_packets=1)
        with self.assertRaises(TypeError):
            runtime.run(max_packets=True)
        runtime.open()
        with self.assertRaises(RuntimeError):
            runtime.open()
        with self.assertRaises(ValueError):
            runtime.run(max_packets=0)
        runtime.close()
        runtime.close()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ground_station"))

from orbitops.recorder import RECORD_VERSION, SessionRecorder, iter_records  # noqa: E402


class RecorderTests(unittest.TestCase):
    def test_record_and_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            with SessionRecorder(path) as recorder:
                recorder.write(b"first", 10.0)
                recorder.write(b"second", 10.5)

            with patch("orbitops.recorder.time.sleep") as sleep:
                records = list(iter_records(path, speed=2.0))

            self.assertEqual(records, [b"first", b"second"])
            sleep.assert_called_once_with(0.25)
            first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(first["record_version"], RECORD_VERSION)

    def test_new_session_replaces_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            path.write_text("stale\n", encoding="utf-8")
            with SessionRecorder(path) as recorder:
                recorder.write(b"new", 1.0)
            self.assertNotIn("stale", path.read_text(encoding="utf-8"))

    def test_unsupported_record_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            path.write_text(
                json.dumps({"record_version": 99, "received_at": 1.0, "packet_hex": "00"}) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unsupported record version"):
                list(iter_records(path))


if __name__ == "__main__":
    unittest.main()

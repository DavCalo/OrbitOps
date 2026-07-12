from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from orbitops.cli import main
from orbitops.link import LinkConfig
from orbitops.profiles import configuration_fingerprint, list_builtin_profiles


class ProfileCliTests(unittest.TestCase):
    def test_list_prints_one_stable_builtin_name_per_line(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["profile", "list"]), 0)

        self.assertEqual(output.getvalue().splitlines(), list(list_builtin_profiles()))

    def test_show_prints_stable_compact_json(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["profile", "show", "nominal"]), 0)

        expected = {
            "description": "Exact pass-through link configuration.",
            "fingerprint": configuration_fingerprint(LinkConfig()),
            "link": {
                "corrupt_rate": 0.0,
                "duplicate_rate": 0.0,
                "jitter_ms": 0,
                "latency_ms": 0,
                "loss_rate": 0.0,
                "reorder_window": 0,
                "seed": 0,
            },
            "name": "nominal",
            "schema_version": 1,
        }
        self.assertEqual(
            output.getvalue(),
            json.dumps(expected, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        )

    def test_validate_accepts_external_profile_and_prints_machine_readable_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "external.toml"
            path.write_text(
                'schema_version = 1\nname = "external"\n[link]\nlatency_ms = 25\n',
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["profile", "validate", str(path)]), 0)

        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "fingerprint": configuration_fingerprint(LinkConfig(latency_ms=25)),
                "name": "external",
                "valid": True,
            },
        )

    def test_show_and_validate_fail_with_actionable_context(self) -> None:
        for operation in ("show", "validate"):
            with (
                self.subTest(operation=operation),
                self.assertRaisesRegex(
                    SystemExit,
                    rf"profile {operation} failed: mission profile reference 'missing'",
                ),
            ):
                main(["profile", operation, "missing"])


if __name__ == "__main__":
    unittest.main()

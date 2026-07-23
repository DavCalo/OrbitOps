#!/usr/bin/env python3
"""Validate the committed session-demo visual against one real installed workflow."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from render_session_demo_visual import parse_capture, render_svg

_ROOT = Path(__file__).resolve().parents[1]
_COMMITTED_VISUAL = _ROOT / "docs" / "assets" / "session-demo.svg"


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} PATH_TO_SIMULATOR", file=sys.stderr)
        return 2

    simulator = Path(sys.argv[1]).resolve()
    if not simulator.is_file():
        print(f"simulator not found: {simulator}", file=sys.stderr)
        return 2

    result = subprocess.run(
        [
            sys.executable,
            str(_ROOT / "scripts" / "session_demo_check.py"),
            str(simulator),
        ],
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=40.0,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "session demo failed while validating the portfolio visual: "
            f"returncode={result.returncode} "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    if result.stderr:
        raise RuntimeError(f"session demo wrote stderr: {result.stderr!r}")

    expected = _COMMITTED_VISUAL.read_text(encoding="utf-8")
    generated = render_svg(parse_capture(result.stdout))
    if generated != expected:
        raise RuntimeError(
            "committed session-demo visual is stale; regenerate it from a real "
            "successful `make session-demo` capture"
        )

    sys.stdout.write(result.stdout)
    print(f"session demo visual ok: {_COMMITTED_VISUAL.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

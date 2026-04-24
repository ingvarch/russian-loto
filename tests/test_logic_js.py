"""Thin wrapper that runs the logic.js test suite via `node --test`.

The real tests live in `tests/js/`. This file exists so `uv run pytest` picks
them up alongside the Python suite. Skipped automatically if node is not on
PATH -- the project does not depend on node; it is only used to test the
pure-JS module that the admin page and future /display page share.
"""

import shutil
import subprocess
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_JS_TESTS = _REPO_ROOT / "tests" / "js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_logic_js_suite_passes():
    """Run Node's built-in test runner on tests/js/ and expect success."""
    result = subprocess.run(
        ["node", "--test", str(_JS_TESTS)],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    if result.returncode != 0:
        pytest.fail(
            f"node --test failed (exit {result.returncode})\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )

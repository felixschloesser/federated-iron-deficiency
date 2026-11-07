"""Plain pytest collects every test: the ones outside the party folders, each
party's under its own settings, and the tests of the tools in .claude/."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.subprocess
def test_plain_pytest_collects_every_party_and_the_tools() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    collected = {
        line.split("::")[0] for line in result.stdout.splitlines() if "::" in line
    }
    folders = {
        path.split("/")[1] if path.startswith("tests/") else path.split("/")[0]
        for path in collected
    }
    assert {"hospital", "practice", "startup", "quality", ".claude"} <= folders, folders

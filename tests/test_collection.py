"""Which tests a run collects: plain pytest those outside the party folders and
says the parties' were not run; a run under a party's settings only that party's."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def collect(*arguments: str) -> tuple[set[str], str]:
    """The top folders under tests/ a collection holds, and its output."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *arguments,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    folders = {
        line.split("::")[0].split("/")[1]
        for line in result.stdout.splitlines()
        if line.startswith("tests/") and "::" in line
    }
    return folders, result.stdout


@pytest.mark.subprocess
def test_plain_pytest_leaves_the_parties_out_and_says_so() -> None:
    folders, output = collect()
    assert "quality" in folders
    assert not {"hospital", "practice", "startup"} & folders
    assert "Party tests not run" in output


@pytest.mark.subprocess
def test_a_partys_run_collects_only_its_own_tests() -> None:
    folders, output = collect("--ds=web.hospital.settings")
    assert "hospital" in folders
    assert not {"practice", "startup"} & folders
    assert "Party tests not run" not in output

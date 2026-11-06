"""Checks each Red: commit: at least one test fails, and only tests that are
new or that the commit changed.

Run before merging a branch: `python .claude/red_first.py [RANGE]` (default
main..HEAD). Each Red: commit and its parent are checked out in temporary
worktrees: the parent's tests are collected, the Red: commit's are run. A test
module is changed when the commit touches it or a feature file it loads.
Container tests are not run, so a Red: commit whose only new tests are
container tests is reported as failing none.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

PYTEST = ["uv", "run", "--frozen", "pytest", "-W", "error", "-p", "no:cacheprovider"]
# A summary line of a failed test or a module that failed to collect.
SUMMARY = re.compile(r"^(?:FAILED|ERROR) (\S+)")


def failing_tests(output: str) -> set[str]:
    """The tests, or test modules, that pytest's short summary reports failing."""
    return {
        match.group(1) for line in output.splitlines() if (match := SUMMARY.match(line))
    }


def collected_tests(output: str) -> set[str]:
    """The test IDs `pytest --collect-only -q` prints."""
    return {line for line in output.splitlines() if "::" in line}


def changed_modules(touched: list[str], modules: dict[str, str]) -> set[str]:
    """The test modules a commit changed: those it touched, and those that load a
    feature file it touched, by its path under features/ as scenarios() names it
    (scenarios("hospital/lab.feature")), given each module's text."""
    features = [
        name.removeprefix("features/") for name in touched if name.endswith(".feature")
    ]
    return {
        module
        for module, text in modules.items()
        if module in touched or any(f'"{feature}"' in text for feature in features)
    }


def problems(failing: set[str], before: set[str], changed: set[str]) -> list[str]:
    """Why a Red: commit is not red first; none when it is. A failing test may be
    new (its parent did not collect it, nor any test of a failing module) or in a
    module the commit changed."""
    if not failing:
        return ["no test fails"]
    return [
        f"{test} fails, but it is neither new nor changed"
        for test in sorted(failing)
        if test.split("::")[0] not in changed
        and any(old == test or old.startswith(f"{test}::") for old in before)
    ]


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout


# One run per party's settings, and one for the tests outside the party
# folders: no run holds two parties (conftest.py).
RUNS: list[list[str]] = [
    *([f"--ds=web.settings.{party}"] for party in ("hospital", "practice", "startup")),
    [],
]


def pytest(tree: Path, *args: str) -> str:
    """Every run's output, one after the other."""
    # Each worktree keeps its own data; a DATA_DIR from the caller would point
    # both at one, and a settings module would choose one party's tests.
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("DATA_DIR", "DJANGO_SETTINGS_MODULE")
    }
    # pytest exits 1 when tests fail, which a Red: commit must.
    return "".join(
        subprocess.run(
            [*PYTEST, *run, *args],
            check=False,
            cwd=tree,
            env=env,
            capture_output=True,
            text=True,
        ).stdout
        for run in RUNS
    )


@contextmanager
def checkout(commit: str) -> Iterator[Path]:
    """The commit in a temporary worktree, removed afterwards."""
    with tempfile.TemporaryDirectory(prefix="red-first-") as folder:
        tree = Path(folder) / "tree"
        git("worktree", "add", "--detach", str(tree), commit)
        try:
            yield tree
        finally:
            git("worktree", "remove", "--force", str(tree))


def check(commit: str) -> list[str]:
    touched = git("diff", "--name-only", f"{commit}^", commit).splitlines()
    with checkout(f"{commit}^") as tree:
        before = collected_tests(pytest(tree, "--collect-only", "-q"))
    with checkout(commit) as tree:
        output = pytest(
            tree, "-q", "--tb=no", "-rfE", "--continue-on-collection-errors"
        )
        modules = {
            path.relative_to(tree).as_posix(): path.read_text()
            for path in (tree / "tests").rglob("test_*.py")
        }
    return problems(failing_tests(output), before, changed_modules(touched, modules))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("range", nargs="?", default="main..HEAD")
    args = parser.parse_args(argv)
    commits = [
        line.split(" ", 1)
        for line in git(
            "log", "--reverse", "--no-merges", "--format=%H %s", args.range
        ).splitlines()
    ]
    red = [(sha, subject) for sha, subject in commits if subject.startswith("Red:")]
    if not red:
        print(f"red_first: no Red: commit in {args.range}")
        return 0
    failed = False
    for sha, subject in red:
        found = check(sha)
        print(f"{sha[:7]} {subject}: {'; '.join(found) if found else 'red first'}")
        failed = failed or bool(found)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

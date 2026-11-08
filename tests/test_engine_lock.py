"""The lock that gives a container run the Docker engine to itself
(tests/compose_project.py): a run that waits says for whom."""

import fcntl
import os
from pathlib import Path

import pytest


def test_the_holder_names_its_checkout_branch_and_process(tmp_path: Path) -> None:
    from tests.compose_project import engine_lock

    lock = tmp_path / "engine.lock"
    with engine_lock(lock, print), lock.open() as other:
        with pytest.raises(BlockingIOError):
            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held = lock.read_text()
    assert str(Path(__file__).resolve().parents[1]) in held
    assert f"pid {os.getpid()}" in held
    assert "since " in held


def test_a_waiting_run_says_whom_it_waits_for(tmp_path: Path) -> None:
    from tests.compose_project import engine_lock

    lock = tmp_path / "engine.lock"
    lock.write_text("/elsewhere (other-branch), pid 1, since 2026-11-08 09:00:00")
    said: list[str] = []
    with lock.open() as other:
        fcntl.flock(other, fcntl.LOCK_EX)
        with (
            pytest.raises(BlockingIOError),
            engine_lock(lock, said.append, wait=False),
        ):
            pass
    waited_for = "/elsewhere (other-branch), pid 1, since 2026-11-08 09:00:00"
    assert said == [f"Waiting for another container run: {waited_for} ({lock})"]

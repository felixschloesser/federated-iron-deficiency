"""Submits training runs to the startup's SuperLink, lists their status and
stops them, by calling the Flower CLI (`flwr run`, `flwr ls`, `flwr stop`)."""

import json
import logging
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, assert_never

from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models

logger = logging.getLogger(__name__)
# Below gunicorn's 30-second worker timeout, so the page can say what happened
# instead of the request ending blank.
SUBMIT_TIMEOUT_SECONDS = 20
# Listing runs is part of loading the page, so a hanging SuperLink must not hang
# the page.
LIST_TIMEOUT_SECONDS = 5
# The SuperLink connection named in FLWR_HOME's config.toml, which the startup's
# image provides (demo/flwr-home/).
CONNECTION = "demo"


def run_configuration(chosen: Mapping[str, int | float | str]) -> str:
    """Format the run configuration for `flwr run --run-config`: the data
    scientist's choices only. There is no threshold, because each hospital's
    threshold follows from its laboratory director's target sensitivity, and no folder, because the ServerApp's
    deployment names where it keeps final models."""
    return " ".join(f"{key}={value!r}" for key, value in chosen.items())


def flower(arguments: list[str], timeout: int) -> dict[str, Any]:
    """Run the Flower CLI with JSON output and return its answer. Raises
    subprocess.TimeoutExpired when the SuperLink does not answer in time."""
    result = subprocess.run(
        [str(Path(sys.executable).parent / "flwr"), *arguments, "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    try:
        answer: dict[str, Any] = json.loads(result.stdout)
    except json.JSONDecodeError:
        # The CLI's error output names server paths, so it goes to the log, not
        # the page.
        logger.error("flwr %s gave no answer: %s", arguments[0], result.stderr.strip())
        return {"error-message": "it gave no answer"}
    return answer


def submit_run(chosen: Mapping[str, int | float | str]) -> int:
    """Submit a training run of this app, configured as chosen; return its run ID."""
    configuration = run_configuration(chosen)
    try:
        answer = flower(
            [
                *("run", str(settings.BASE_DIR), CONNECTION),
                *(("--run-config", configuration) if configuration else ()),
            ],
            SUBMIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise ValidationError(
            {
                NON_FIELD_ERRORS: ValidationError(
                    f"The SuperLink did not answer within {SUBMIT_TIMEOUT_SECONDS}"
                    " seconds; the run may or may not have been submitted: check the"
                    " training runs below before submitting again.",
                    code="superlink_no_answer",
                )
            }
        ) from error
    if not answer.get("success"):
        # An error of the whole submission, not of a field.
        raise ValidationError(
            {
                NON_FIELD_ERRORS: ValidationError(
                    f"The SuperLink refused the run: {answer.get('error-message')}",
                    code="superlink_refused",
                )
            }
        )
    return int(answer["run-id"])


def stop_run(run_id: int) -> None:
    """Stop a training run in progress."""
    try:
        answer = flower(["stop", str(run_id), CONNECTION], SUBMIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        raise ValidationError(
            f"The SuperLink did not answer within {SUBMIT_TIMEOUT_SECONDS} seconds;"
            f" training run {run_id} may or may not have stopped: check its status"
            " below.",
            code="superlink_no_answer",
        ) from error
    if not answer.get("success"):
        raise ValidationError(
            f"The SuperLink did not stop training run {run_id}:"
            f" {answer.get('error-message')}",
            code="superlink_refused_stop",
        )


class RunStatus(models.TextChoices):
    """Where a training run is, in Flower's words (`flwr ls`)."""

    PENDING = "pending", "Pending"
    STARTING = "starting", "Starting"
    RUNNING = "running", "Running"
    COMPLETED = "finished:completed", "Completed"
    FAILED = "finished:failed", "Failed"
    STOPPED = "finished:stopped", "Stopped"

    @property
    def in_progress(self) -> bool:
        """Whether the run has not finished yet; the page highlights such runs."""
        match self:
            case RunStatus.PENDING | RunStatus.STARTING | RunStatus.RUNNING:
                return True
            case RunStatus.COMPLETED | RunStatus.FAILED | RunStatus.STOPPED:
                return False
            case _:
                assert_never(self)


def flower_time(text: str) -> datetime | None:
    """Parse a time as `flwr ls` gives it; None for "N/A", a state not reached."""
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


@dataclass(frozen=True)
class TrainingRun:
    """A training run as the SuperLink reports it."""

    run_id: int
    # None for a status this app does not know; status_label then shows
    # Flower's own text.
    status: RunStatus | None
    status_text: str
    # When it was submitted (Flower's "pending"), and when it reached its status.
    submitted_at: datetime | None
    since: datetime | None
    elapsed: timedelta
    details: str | None

    @classmethod
    def from_flower(cls, run: dict[str, Any]) -> "TrainingRun":
        text = str(run["status"])
        reached = [
            flower_time(str(run.get(f"{state}-at", "N/A")))
            for state in ("finished", "running", "starting", "pending")
        ]
        details = str(run.get("status-details", "N/A"))
        return cls(
            run_id=int(run["run-id"]),
            status=RunStatus(text) if text in RunStatus.values else None,
            status_text=text,
            submitted_at=reached[-1],
            since=next((time for time in reached if time is not None), None),
            elapsed=timedelta(seconds=int(float(run.get("elapsed", 0)))),
            details=None if details == "N/A" else details,
        )

    @property
    def status_label(self) -> str:
        return self.status_text if self.status is None else str(self.status.label)


def training_runs() -> list[TrainingRun]:
    """Every training run the SuperLink knows, newest first."""
    try:
        answer = flower(["ls", CONNECTION], LIST_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        raise ValidationError(
            f"The SuperLink did not answer within {LIST_TIMEOUT_SECONDS} seconds,"
            " so the training runs' statuses are unknown.",
            code="superlink_no_answer",
        ) from error
    if not answer.get("success"):
        # The error message names the SuperLink's address, so it goes to the log,
        # not the page.
        logger.error("flwr ls failed: %s", answer.get("error-message"))
        raise ValidationError(
            "The SuperLink is unavailable, so the training runs' statuses are unknown.",
            code="superlink_unavailable",
        )
    runs = [TrainingRun.from_flower(run) for run in answer.get("runs", [])]
    # Run IDs are random, so sort by submission time to put the newest first.
    return sorted(
        runs,
        key=lambda run: (run.submitted_at is not None, run.submitted_at),
        reverse=True,
    )

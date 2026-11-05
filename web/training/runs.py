"""Submitting a training run to the startup's SuperLink (DF4), as `flwr run` does."""

import json
import logging
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError

logger = logging.getLogger(__name__)
# Under gunicorn's worker timeout (30 s): the page says why instead of the
# request ending blank.
SUBMIT_TIMEOUT_SECONDS = 20
# The SuperLink connection in FLWR_HOME's config.toml (demo/demo.py writes it).
CONNECTION = "demo"


def run_configuration(threshold: float) -> str:
    """The run configuration the ServerApp reads: the threshold it sends every
    hospital, and, in a deployment, the demo folder above the startup's."""
    parts = [f"screening-threshold={threshold}"]
    if settings.STARTUP_DIR is not None:
        parts.insert(0, f"demo-dir='{settings.STARTUP_DIR.parent}'")
    return " ".join(parts)


def submit_run(*, threshold: float) -> int:
    """Submit one training run of this app with the threshold; return its run ID."""
    if threshold <= 0:
        raise ValidationError(
            {
                "threshold": ValidationError(
                    "The threshold must be above 0.", code="threshold_not_above_zero"
                )
            }
        )
    if threshold >= 1:
        raise ValidationError(
            {
                "threshold": ValidationError(
                    "The threshold must be below 1.", code="threshold_not_below_one"
                )
            }
        )
    try:
        result = subprocess.run(
            [
                str(Path(sys.executable).parent / "flwr"),
                *("run", str(settings.BASE_DIR), CONNECTION),
                *("--run-config", run_configuration(threshold), "--format", "json"),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=SUBMIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise ValidationError(
            {
                NON_FIELD_ERRORS: ValidationError(
                    f"The SuperLink did not answer within {SUBMIT_TIMEOUT_SECONDS}"
                    " seconds; the run may or may not have been submitted.",
                    code="superlink_no_answer",
                )
            }
        ) from error
    try:
        answer = json.loads(result.stdout)
    except json.JSONDecodeError:
        # The CLI's own output names server paths: for the log, not the page.
        logger.error("flwr run gave no answer: %s", result.stderr.strip())
        answer = {"error-message": "it gave no answer"}
    if not answer.get("success"):
        # Not the threshold's fault: an error of the whole submission.
        raise ValidationError(
            {
                NON_FIELD_ERRORS: ValidationError(
                    f"The SuperLink refused the run: {answer.get('error-message')}",
                    code="superlink_refused",
                )
            }
        )
    return int(answer["run-id"])

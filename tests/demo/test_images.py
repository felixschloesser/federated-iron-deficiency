"""What the container images install (demo/README.md)."""

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_no_gpu_libraries_are_locked_for_any_platform() -> None:
    # Torch on Linux comes from PyTorch's CPU index: an x86-64 image would
    # otherwise pull several GB of CUDA libraries that screening never uses.
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    names = {package["name"] for package in lock["package"]}
    gpu = {name for name in names if name.startswith(("nvidia-", "cuda-", "triton"))}
    assert gpu == set()


def test_the_practice_image_installs_only_the_web_apps_dependencies() -> None:
    """A practice screens nothing: its image has no PyTorch, Flower or W&B."""
    dockerfile = (ROOT / "demo" / "practice-web.Dockerfile").read_text()
    (sync,) = [
        line.split("uv sync", 1)[1].split()
        for line in dockerfile.splitlines()
        if "uv sync" in line
    ]
    export = subprocess.run(
        ["uv", "export", *sync, "--no-hashes", "--no-header", "--no-annotate"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    names = {
        re.split(r"[=<>;\s]", line, maxsplit=1)[0].lower()
        for line in export.splitlines()
        if line and not line.startswith(("#", " ", "-"))
    }
    assert names.isdisjoint({"torch", "flwr", "wandb", "datasets"}), names
    assert {"django", "grpcio", "protobuf", "gunicorn", "whitenoise"} <= names


def test_django_boots_without_the_training_data_libraries() -> None:
    """Both parties' apps and URLs load without Hugging Face's datasets."""
    code = (
        "import sys, django; django.setup();"
        " from django.urls import get_resolver; get_resolver().url_patterns;"
        " print(sorted(m for m in ('datasets', 'flwr_datasets') if m in sys.modules))"
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PARTY", "DATA_DIR"}
    }
    environment["DJANGO_SETTINGS_MODULE"] = "web.settings"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "[]"

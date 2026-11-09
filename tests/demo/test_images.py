"""What the container images install (demo/README.md)."""

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.subprocess

ROOT = Path(__file__).resolve().parents[2]


def test_no_gpu_libraries_are_locked_for_any_platform() -> None:
    # Torch on Linux comes from PyTorch's CPU index: an x86-64 image would
    # otherwise pull several GB of CUDA libraries that screening never uses.
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    names = {package["name"] for package in lock["package"]}
    gpu = {name for name in names if name.startswith(("nvidia-", "cuda-", "triton"))}
    assert gpu == set()


def locked(sync: list[str]) -> set[str]:
    """The packages `uv sync` with these arguments installs, by name."""
    export = subprocess.run(
        ["uv", "export", *sync, "--no-hashes", "--no-header", "--no-annotate"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {
        re.split(r"[=<>;\s]", line, maxsplit=1)[0].lower()
        for line in export.splitlines()
        if line and not line.startswith(("#", " ", "-"))
    }


def test_the_practice_image_installs_only_the_web_apps_dependencies() -> None:
    """A practice screens nothing: its image has no PyTorch, Flower or W&B."""
    dockerfile = (ROOT / "demo" / "practice.Dockerfile").read_text()
    (sync,) = [
        line.split("uv sync", 1)[1].split()
        for line in dockerfile.splitlines()
        if "uv sync" in line
    ]
    names = locked(sync)
    assert names.isdisjoint({"torch", "flwr", "wandb", "datasets"}), names
    assert {"django", "grpcio", "protobuf", "gunicorn", "whitenoise"} <= names


@pytest.mark.parametrize("party", ["hospital", "startup"])
def test_the_training_images_install_no_plotting_or_dataset_framework(
    party: str,
) -> None:
    """The training package reads its cohort with pandas: an image brings no
    plotting library and no dataset framework it never calls."""
    dockerfile = (ROOT / "demo" / f"{party}.Dockerfile").read_text()
    sync = next(
        line.split("uv sync", 1)[1].split()
        for line in dockerfile.splitlines()
        if "uv sync" in line
    )
    names = locked(sync)
    assert {"torch", "flwr", "pandas", "pyarrow"} <= names
    assert names.isdisjoint({"matplotlib", "seaborn", "datasets", "flwr-datasets"}), (
        names
    )


@pytest.mark.parametrize("party", ["hospital", "practice", "startup"])
def test_django_boots_without_the_training_data_libraries(party: str) -> None:
    """Each party's apps and URLs load without Hugging Face's datasets."""
    code = (
        "import sys, django; django.setup();"
        " from django.urls import get_resolver; get_resolver().url_patterns;"
        " print(sorted(m for m in ('datasets', 'flwr_datasets') if m in sys.modules))"
    )
    environment = {key: value for key, value in os.environ.items() if key != "DATA_DIR"}
    environment["DJANGO_SETTINGS_MODULE"] = f"web.{party}.settings"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "[]"


# What each party's folder may hold: the report's DFD stores, and the Django
# secret key its web app uses (demo/README.md).
PARTY_FOLDERS = {
    "startup": {
        "superlink",  # the SuperLink's own state, no DFD store
        "final-models",  # DS4
        "flwr-home",
        "web.sqlite3",  # the data scientist's account
        ".secret_key",
    },
    "hospital": {
        "cohort",  # DS2
        "screening-models",  # DS5
        "web.sqlite3",  # DS1, DS6, DS8, DS9
        ".secret_key",
    },
    "practice": {"web.sqlite3", ".secret_key"},  # DS7
}


@pytest.mark.parametrize("party", sorted(PARTY_FOLDERS))
def test_each_image_brings_only_its_partys_dfd_stores(party: str) -> None:
    """Docker copies the folders a party's image makes under /data into its fresh
    volume: only the party's own stores."""
    dockerfile = (ROOT / "demo" / f"{party}.Dockerfile").read_text()
    made = " ".join(re.findall(r"^RUN mkdir -p (.+)$", dockerfile, re.MULTILINE))
    folders = {path.removeprefix("/data/") for path in made.split()}
    assert folders <= PARTY_FOLDERS[party]


@pytest.mark.parametrize("party", sorted(PARTY_FOLDERS))
def test_no_party_image_wraps_its_servers_in_a_start_script(party: str) -> None:
    """compose.yaml's setup job sets the party up; a server is only its command."""
    dockerfile = (ROOT / "demo" / f"{party}.Dockerfile").read_text()
    assert "ENTRYPOINT" not in dockerfile


def test_the_startup_image_brings_its_command_lines_superlink() -> None:
    """The data scientist's flwr reaches the SuperLink in plaintext: the report's
    TLS and SuperNode authentication are left out of the demo. The image brings
    the connection into the startup's fresh volume, as it brings its folders."""
    config = tomllib.loads((ROOT / "demo" / "flwr-home" / "config.toml").read_text())
    assert config["superlink"] == {
        "default": "demo",
        "demo": {"address": "flower-superlink:9092", "insecure": True},
    }
    dockerfile = (ROOT / "demo" / "startup.Dockerfile").read_text()
    assert (
        "COPY --chown=app demo/flwr-home/config.toml /data/flwr-home/config.toml"
        in dockerfile
    )

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
    (made,) = re.findall(r"install -d -o app (.+)$", dockerfile, re.MULTILINE)
    folders = {
        path.removeprefix("/data/")
        for path in made.split()
        if path.startswith("/data/")
    }
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


OUR_IMAGES = ["hospital", "practice", "startup", "nhanes-download"]


@pytest.mark.parametrize("image", OUR_IMAGES)
def test_each_image_makes_the_user_compose_runs_as(image: str) -> None:
    """compose.yaml runs every container as 1000:1000, who must own the folders
    each image brings: the image names that UID instead of trusting useradd's
    first free one."""
    dockerfile = (ROOT / "demo" / f"{image}.Dockerfile").read_text()
    assert "useradd --uid 1000 --create-home app" in dockerfile


@pytest.mark.parametrize("image", ["hospital", "practice", "startup"])
def test_each_party_image_installs_its_dependencies_once_and_not_the_project(
    image: str,
) -> None:
    """The code runs from /app as it is copied: one sync, without the project."""
    dockerfile = (ROOT / "demo" / f"{image}.Dockerfile").read_text()
    syncs = [line for line in dockerfile.splitlines() if "uv sync" in line]
    assert len(syncs) == 1, syncs
    assert "--no-install-project" in syncs[0] or "--only-group" in syncs[0]


@pytest.mark.parametrize("image", ["hospital", "practice", "startup"])
def test_only_the_startup_image_brings_what_its_fab_includes(image: str) -> None:
    """The data scientist's flwr builds the FAB from the startup's /app, and the
    FAB includes pyproject.toml's fab-include; no other party builds one."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    included = pyproject["tool"]["flwr"]["app"]["fab-include"]
    files = [pattern.removeprefix("/") for pattern in included if "*" not in pattern]
    dockerfile = (ROOT / "demo" / f"{image}.Dockerfile").read_text()
    for name in files:
        assert (name in dockerfile) is (image == "startup"), name


def test_the_superexec_image_installs_only_the_locked_files() -> None:
    """Threat: a changed package on an index reaching the image that runs the
    startup's code at every hospital. Pass: pip installs with uv.lock's hashes."""
    dockerfile = (ROOT / "demo" / "superexec.Dockerfile").read_text()
    assert "--no-hashes" not in dockerfile
    assert "--require-hashes" in dockerfile


@pytest.mark.parametrize("image", OUR_IMAGES)
def test_each_image_starts_from_one_python_release(image: str) -> None:
    """A rebuild months later gets the same Python as today's: the base image
    names its patch release, the same in every image."""
    dockerfile = (ROOT / "demo" / f"{image}.Dockerfile").read_text()
    assert re.findall(r"^FROM (\S+)", dockerfile, re.MULTILINE) == [
        "python:3.13.18-slim"
    ]

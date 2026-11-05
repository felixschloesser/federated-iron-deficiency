"""What the container images install (spec §9)."""

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

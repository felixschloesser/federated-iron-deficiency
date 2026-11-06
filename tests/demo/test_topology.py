"""The committed compose.yaml and proxy.conf are what demo/topology.py generates
from demo.toml and the hospitals training knows."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.subprocess
def test_the_committed_topology_is_what_demo_toml_generates(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "demo.topology", "--out", str(tmp_path)],
        cwd=ROOT,
        check=True,
    )
    for name in ("compose.yaml", "proxy.conf"):
        committed = (ROOT / "demo" / name).read_text()
        assert (tmp_path / name).read_text() == committed, (
            f"demo/{name} is stale: run `python -m demo.topology`"
        )


@pytest.mark.parametrize(
    "declared",
    [
        pytest.param({"uz-leuven": {}, "az-diest": {}}, id="a hospital missing"),
        pytest.param(
            {"uz-leuven": {}, "heilig-hart-leuven": {}, "az-diest": {}, "x": {}},
            id="a hospital training does not know",
        ),
    ],
)
def test_demo_toml_must_declare_exactly_the_hospitals_training_knows(
    declared: dict[str, dict[str, object]],
) -> None:
    from demo.topology import by_cycle

    with pytest.raises(ValueError, match="training knows"):
        by_cycle(declared)

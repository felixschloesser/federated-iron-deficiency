"""Checks that the Flower App Bundle ships only the federated app."""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_fab_holds_only_the_federated_app(tmp_path):
    app = tmp_path / "app"  # flwr requires a valid app name for the directory
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    for name in tracked:
        (app / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, app / name)
    # Stand-ins for the web app, which must never reach a SuperNode.
    (app / "web").mkdir()
    (app / "web" / "settings.py").write_text("DEBUG = False\n")

    flwr = Path(sys.executable).parent / "flwr"
    subprocess.run([str(flwr), "build"], cwd=app, capture_output=True, check=True)

    (fab,) = app.glob("*.fab")
    names = set(zipfile.ZipFile(fab).namelist()) - {".info/CONTENT"}
    shipped = {"pyproject.toml", "LICENSE", "README.md"}
    assert names - shipped, "the FAB holds no app code"
    assert all(
        name in shipped or name.startswith(("iron_deficiency/", "scripts/"))
        for name in names
    ), sorted(names)

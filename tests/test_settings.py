"""Settings keep a hospital's web app inside its own folder (spec R21)."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_ENV = {
    name: value
    for name, value in os.environ.items()
    if name not in {"DATABASE_NAME", "HOSPITAL_DIR"}
}


def database_path(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    code = (
        "from django.conf import settings; print(settings.DATABASES['default']['NAME'])"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        cwd=ROOT,
        env={**BASE_ENV, "DJANGO_SETTINGS_MODULE": "web.settings", **env},
        capture_output=True,
        text=True,
    )


def test_the_database_lives_in_the_hospital_folder(tmp_path: Path) -> None:
    result = database_path({"HOSPITAL_DIR": str(tmp_path)})
    assert result.stdout.strip() == str(tmp_path / "web.sqlite3")


def test_a_database_elsewhere_is_refused(tmp_path: Path) -> None:
    result = database_path({"HOSPITAL_DIR": str(tmp_path), "DATABASE_NAME": "other"})
    assert result.returncode != 0
    assert "HOSPITAL_DIR" in result.stderr

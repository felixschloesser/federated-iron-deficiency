"""A party's web container's start (demo/README.md): it sets itself up, then
starts its servers. Each party's image runs it as its entrypoint, with the
servers as its command:

    python -m demo.party SERVER-COMMAND...

From its own environment, in compose.yaml:

- DJANGO_SETTINGS_MODULE and DATA_DIR: which party, and its folder, whose
  layout the image brought (Docker copies it into a fresh volume).
- DEMO_REGISTER: who it knows, one manage.py command a line (add_practice,
  add_laboratory or add_hospital), as each party would type them.
- DEMO_PROVIDE: a hospital whose laboratory director provided the training
  cohort.
- DEMO_ADDRESS: where its pages are, for the line it prints when ready.

Its public NHANES extract, nhanes-download's, is read-only at /nhanes. Each
step is idempotent, so a restart is quick.
"""

import os
import shlex
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NHANES = Path("/nhanes")
# What a party may register at start: the commands its people would run.
REGISTRATIONS = {"add_practice", "add_laboratory", "add_hospital"}
# The startup's command line reaches its SuperLink in plaintext: the report's
# TLS and SuperNode authentication are left out of the demo for simplicity.
FLWR_CONFIG = (
    '[superlink]\ndefault = "demo"\n\n[superlink.demo]\n'
    'address = "flower-superlink:9092"\ninsecure = true\n'
)


def set_aside_stale_database(folder: Path) -> Path | None:
    """Rename the party's database aside when it records a migration of ours the
    code no longer has (a volume from before migrations were reset): it cannot
    migrate. The renamed file is kept; returns where it went."""
    path = folder / "web.sqlite3"
    if not path.exists():
        return None
    ours = {
        (migration.parent.parent.name, migration.stem)
        for migration in (ROOT / "web").glob("**/migrations/0*.py")
    }
    labels = {app for app, _ in ours}
    database = sqlite3.connect(path)
    try:
        recorded = database.execute(
            "SELECT app, name FROM django_migrations"
        ).fetchall()
    except sqlite3.OperationalError:
        # No table yet: migrate never finished on it, and will start it.
        recorded = []
    finally:
        database.close()
    if all(app not in labels or (app, name) in ours for app, name in recorded):
        return None
    aside = path.with_name("web.sqlite3.before-reset")
    path.rename(aside)
    return aside


def registrations(text: str) -> list[list[str]]:
    """DEMO_REGISTER's commands; any other command is refused."""
    commands = [shlex.split(line) for line in text.splitlines() if line.strip()]
    for command in commands:
        if command[0] not in REGISTRATIONS:
            raise SystemExit(f"DEMO_REGISTER may not run {command[0]}.")
    return commands


def seeding(party: str, environment: dict[str, str]) -> list[list[str]]:
    """The seed commands for `party`, from its NHANES extract."""
    match party:
        case "hospital":
            provide = ["--provide"] if environment.get("DEMO_PROVIDE") == "1" else []
            return [
                ["hospital", "--rows", str(NHANES / "participants.csv")],
                ["lab-records", "--csv", str(NHANES / "lab-records.csv"), *provide],
            ]
        case "practice":
            return [["practice", "--rows", str(NHANES / "patients.csv")]]
        case "startup":
            return [["startup"]]
        case _:
            raise SystemExit(f"No demo party {party}.")


def run(command: list[str], environment: dict[str, str]) -> str:
    """Run a setup step, its output kept unless it fails."""
    result = subprocess.run(
        command, env=environment, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(result.returncode)
    return result.stdout


def set_up(environment: dict[str, str]) -> str:
    """Migrate, seed and register the party; what it seeded, for its line."""
    party = environment["DJANGO_SETTINGS_MODULE"].split(".")[1]
    folder = Path(environment["DATA_DIR"])
    aside = set_aside_stale_database(folder)
    if aside is not None:
        print(f"Its database predates the code's migrations; kept as {aside.name}.")
    # The demo's accounts share a known password: seeding runs in DEBUG only.
    setup = {**environment, "DJANGO_DEBUG": "1"}
    manage = [sys.executable, str(ROOT / "manage.py")]
    run([*manage, "migrate", "-v0"], setup)
    seeded = [
        run([sys.executable, "-m", "demo.seed", *arguments], setup).strip()
        for arguments in seeding(party, environment)
    ]
    for command in registrations(environment.get("DEMO_REGISTER", "")):
        run([*manage, *command], setup)
    if party == "startup":
        (folder / "flwr-home" / "config.toml").write_text(FLWR_CONFIG)
    return seeded[0]


def main(argv: list[str]) -> None:
    if not argv:
        raise SystemExit("Give the servers to start: python -m demo.party COMMAND...")
    environment = dict(os.environ)
    seeded = set_up(environment)
    address = environment.get("DEMO_ADDRESS", "")
    name = (
        environment.get("PRACTICE_NAME")
        or environment.get("HOSPITAL_NAME")
        or environment.get("STARTUP_NAME")
        or "The startup"
    )
    print(f"{name} ready at {address}: {seeded}", flush=True)
    os.execvp(argv[0], argv)


if __name__ == "__main__":
    main(sys.argv[1:])

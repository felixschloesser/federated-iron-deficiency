"""The demo's preparation helpers (spec §9); compose.yaml is in tests/test_compose.py."""

from pathlib import Path


def test_reset_removes_only_the_web_databases(tmp_path: Path) -> None:
    from tools.demo import hospital_dir, practice_dir, reset

    kept = []
    removed = []
    for folder in (hospital_dir(tmp_path, "uz-leuven"), practice_dir(tmp_path, "a")):
        (folder / "certificates").mkdir(parents=True)
        for name in ("nhanes.csv", "certificates/ca.crt"):
            (folder / name).write_text("keep")
            kept.append(folder / name)
        (folder / "web.sqlite3").write_text("old")
        removed.append(folder / "web.sqlite3")
    reset(tmp_path, demo_running=lambda: False)
    assert all(path.exists() for path in kept)
    assert not any(path.exists() for path in removed)


def test_reset_refuses_while_the_demo_runs(tmp_path: Path) -> None:
    import pytest

    from tools.demo import hospital_dir, reset

    database = hospital_dir(tmp_path, "uz-leuven") / "web.sqlite3"
    database.parent.mkdir(parents=True)
    database.write_text("in use")
    with pytest.raises(SystemExit, match="Stop the demo"):
        reset(tmp_path, demo_running=lambda: True)
    assert database.exists()


STATUSES = {
    "uz-leuven": "2 screening models, none deployed",
    "heilig-hart-leuven": "no screening model yet",
    "az-diest": "Screening model of 29 Oct 2026, 20:55 deployed (1 in all)",
}


def test_the_summary_names_each_party_with_its_address_and_state() -> None:
    from tools.demo import summary

    text = summary(STATUSES)
    assert "Password for every account: demo-pass-2026" in text
    assert "laboratory staff: lab-1 · laboratory director: director-1" in text
    assert "general practitioners: doctor-a, doctor-b" in text
    for line in (
        "UZ Leuven  ",
        "https://127.0.0.1:8001/   2 screening models, none deployed",
        "https://127.0.0.1:8002/   no screening model yet",
        "Huisartsenpraktijk De Akker → UZ Leuven",
        "https://127.0.0.1:8013/",
        "Ctrl-C stops every party.",
    ):
        assert line in text, line
    assert "Accounts" not in text


def test_the_next_step_follows_the_hospitals_state() -> None:
    from tools.demo import summary

    assert "Next: train with `docker compose run --rm train`" in summary(STATUSES)
    trained = {**STATUSES, "heilig-hart-leuven": "1 screening model, none deployed"}
    assert "Next: deploy a screening model as director-1" in summary(trained)
    deployed = dict.fromkeys(STATUSES, "Screening model of … deployed (1 in all)")
    assert "Next:" not in summary(deployed)


def test_each_practice_and_its_hospital_seed_the_same_number_of_patients() -> None:
    from tools.demo import PATIENTS, seed_arguments

    assert [PATIENTS[cycle] for cycle in PATIENTS] == [40, 24, 12]
    for partition, cycle in enumerate(PATIENTS):
        arguments = seed_arguments(partition, Path("nhanes.csv"))
        assert arguments[arguments.index("--patients") + 1] == str(PATIENTS[cycle])


def test_each_web_app_gets_a_certificate_from_the_browser_ca_kept_outside_every_party(
    tmp_path: Path,
) -> None:
    import subprocess

    from tools.certificates import covers
    from tools.demo import browser_ca, hospitals, practices, prepare_browser, web_tls

    prepare_browser(tmp_path)
    authority = browser_ca(tmp_path)
    folders = [tmp_path / "hospitals" / slug for _, slug in hospitals()]
    folders += [tmp_path / "practices" / slug for _, slug in practices()]
    for folder in folders:
        certificate = web_tls(folder) / "certificate.pem"
        subprocess.run(
            [
                "openssl",
                "verify",
                "-CAfile",
                str(authority / "ca.crt"),
                str(certificate),
            ],
            check=True,
            capture_output=True,
        )
        # The browser asks for 127.0.0.1; HSTS never pins an IP address.
        assert covers(certificate, "localhost")
        assert (web_tls(folder) / "key.pem").stat().st_mode & 0o777 == 0o600
        assert not (folder / "ca.key").exists()
    assert not authority.is_relative_to(tmp_path / "hospitals")
    assert not authority.is_relative_to(tmp_path / "practices")


def test_preparing_again_keeps_each_web_apps_certificate(tmp_path: Path) -> None:
    from tools.demo import prepare_browser, web_tls

    prepare_browser(tmp_path)
    certificate = web_tls(tmp_path / "hospitals" / "uz-leuven") / "certificate.pem"
    first = certificate.read_bytes()
    prepare_browser(tmp_path)
    assert certificate.read_bytes() == first

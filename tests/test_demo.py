"""The demo's preparation helpers (spec §9); compose.yaml is in tests/test_compose.py."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
    assert "general practitioner: doctor" in text
    for line in (
        "UZ Leuven  ",
        "https://uz-leuven.localhost/   2 screening models, none deployed",
        "https://heilig-hart-leuven.localhost/   no screening model yet",
        "Huisartsenpraktijk De Akker → UZ Leuven",
        "https://huisartsenpraktijk-de-ceder.localhost/",
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
        # The browser asks for <party>.localhost, which the CA's constraint permits.
        assert covers(certificate, f"{folder.name}.localhost")
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


def test_the_browser_ca_vouches_only_for_localhost(tmp_path: Path) -> None:
    import subprocess

    from tools.certificates import Authority, issue
    from tools.demo import browser_ca, prepare_browser

    prepare_browser(tmp_path)
    folder = browser_ca(tmp_path)
    authority = Authority("Demo browser", folder / "ca.crt", folder / "ca.key")
    # Whoever reads the key may sign for any name; browsers accept only localhost.
    certificate, _ = issue(authority, tmp_path / "bank", "bank.example", server=True)
    verified = subprocess.run(
        ["openssl", "verify", "-CAfile", str(authority.certificate), str(certificate)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert verified.returncode != 0
    assert "subtree violation" in verified.stdout + verified.stderr


def test_mkcert_finds_the_browser_ca_but_not_its_key(tmp_path: Path) -> None:
    from tools.demo import browser_ca, prepare_browser

    prepare_browser(tmp_path)
    folder = browser_ca(tmp_path)
    # `CAROOT=demo/browser-ca mkcert -install` trusts rootCA.pem; without
    # rootCA-key.pem mkcert only installs and never issues ("keyless mode").
    assert (folder / "rootCA.pem").read_bytes() == (folder / "ca.crt").read_bytes()
    assert not (folder / "rootCA-key.pem").exists()


def test_the_summary_names_the_https_port_when_it_is_not_443() -> None:
    from tools.demo import summary

    text = summary(STATUSES, https_port=8443)
    assert "https://uz-leuven.localhost:8443/" in text


def test_demo_toml_describes_exactly_the_hospitals_training_knows() -> None:
    import tomllib

    from iron_deficiency.dataset import HOSPITALS, hospital_slug

    parties = tomllib.loads((ROOT / "demo.toml").read_text())
    assert set(parties["hospitals"]) == {hospital_slug(n) for n in HOSPITALS.values()}


def test_each_hospitals_practice_colours_and_patients_come_from_demo_toml() -> None:
    import tomllib

    from iron_deficiency.dataset import HOSPITALS, hospital_slug
    from tools.demo import COLOURS, PATIENTS, PRACTICES

    hospitals = tomllib.loads((ROOT / "demo.toml").read_text())["hospitals"]
    for cycle, name in HOSPITALS.items():
        entry = hospitals[hospital_slug(name)]
        assert PRACTICES[cycle] == entry["practice"]
        assert COLOURS[cycle] == (entry["colour"], entry["practice_colour"])
        assert PATIENTS[cycle] == entry["patients"]

"""Only the hospitals' registered SuperNodes join the federation (spec R27, O20).

The running check, a stranger refused and the hospital admitted, is in
tests/test_containers.py.
"""

from pathlib import Path

import pytest

from iron_deficiency.dataset import HOSPITALS, hospital_slug
from tests.test_compose import mounts, service
from tools import demo

HOSPITAL_SLUGS = sorted(hospital_slug(name) for name in HOSPITALS.values())


def test_the_superlink_admits_only_registered_supernodes() -> None:
    assert "--enable-supernode-auth" in service("superlink")["command"]


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS)
def test_each_supernode_signs_in_with_its_hospitals_own_key(slug: str) -> None:
    key = demo.supernode_key(demo.hospital_dir(Path("/demo"), slug))
    assert (
        f"--auth-supernode-private-key={key}" in service(f"{slug}-supernode")["command"]
    )
    # The key is the hospital's own, mounted read-only into its SuperNode alone.
    assert mounts(f"{slug}-supernode")[str(key.parent)] == (
        f"hospitals/{slug}/supernode",
        True,
    )


def test_each_hospital_keeps_its_private_key_and_hands_the_startup_its_public_one(
    tmp_path: Path,
) -> None:
    demo.prepare_flower(tmp_path)
    for slug in HOSPITAL_SLUGS:
        key = demo.supernode_key(demo.hospital_dir(tmp_path, slug))
        assert key.stat().st_mode & 0o777 == 0o600
        registered = demo.registered_key(tmp_path, slug)
        assert registered.read_bytes() == key.with_suffix(".pub").read_bytes()
    startup = demo.startup_dir(tmp_path)
    assert all(path.suffix == ".pub" for path in (startup / "supernodes").iterdir())


def test_preparing_again_keeps_each_hospitals_key(tmp_path: Path) -> None:
    demo.prepare_flower(tmp_path)
    key = demo.supernode_key(demo.hospital_dir(tmp_path, HOSPITAL_SLUGS[0]))
    first = key.read_bytes()
    demo.prepare_flower(tmp_path)
    assert key.read_bytes() == first

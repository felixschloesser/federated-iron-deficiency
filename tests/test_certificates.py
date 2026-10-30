"""The demo's certificate authorities and certificates (tools/certificates.py)."""

import stat
from pathlib import Path

from tools.certificates import issue, make_authority


def test_private_keys_are_readable_by_their_owner_only(tmp_path: Path) -> None:
    # Whatever the openssl build's default: a hospital's CA key sits in the folder
    # its web app and messaging endpoint read.
    authority = make_authority(tmp_path / "ca", "Test hospital")
    _, key = issue(authority, tmp_path / "server", "localhost", server=True)
    for path in (authority.key, key):
        path.chmod(0o644)
    authority = make_authority(tmp_path / "ca", "Test hospital")
    _, key = issue(authority, tmp_path / "server", "localhost", server=True)
    for path in (authority.key, key):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, path

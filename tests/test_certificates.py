"""The demo's certificate authorities and certificates (tools/certificates.py)."""

import shutil
import stat
import subprocess
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


def public_key(path: Path, *, certificate: bool) -> str:
    """The public key in a certificate, or of a private key."""
    command = (
        ["openssl", "x509", "-in", str(path), "-noout", "-pubkey"]
        if certificate
        else ["openssl", "pkey", "-in", str(path), "-pubout"]
    )
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout


def test_the_authority_signs_a_request_and_never_needs_the_private_key(
    tmp_path: Path,
) -> None:
    """The owner makes its key pair and a request; the authority gets the request
    alone, as a practice sends a hospital (R24), and returns a certificate."""
    from tools.certificates import request, sign

    authority = make_authority(tmp_path / "ca", "Test hospital")
    owner = tmp_path / "practice"
    request_file = request(owner, "Huisartsenpraktijk De Ceder")
    inbox = tmp_path / "hospital-inbox"
    inbox.mkdir()
    shutil.copy(request_file, inbox / "request.csr")
    certificate = sign(authority, inbox / "request.csr", server=False)
    assert sorted(path.name for path in inbox.iterdir()) == [
        "certificate.pem",
        "request.csr",
    ]
    assert (owner / "key.pem").exists()
    assert public_key(certificate, certificate=True) == public_key(
        owner / "key.pem", certificate=False
    )

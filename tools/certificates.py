"""Certificate authorities and certificates for the demo, made with openssl.

Each hospital is its own authority (spec R24): it issues its messaging
endpoint's server certificate and its general practitioner's client one.
"""

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

DAYS = "30"


@dataclass(frozen=True)
class Authority:
    name: str
    certificate: Path
    key: Path


def _openssl(directory: Path, *args: str) -> None:
    subprocess.run(["openssl", *args], cwd=directory, check=True, capture_output=True)


def make_authority(directory: Path, name: str) -> Authority:
    """A self-signed certificate authority in `directory`."""
    directory.mkdir(parents=True, exist_ok=True)
    _openssl(
        directory,
        *("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", DAYS),
        *("-subj", f"/CN={name} certificate authority"),
        *("-keyout", "ca.key", "-out", "ca.crt"),
    )
    # Owner only, whatever the openssl build's default.
    (directory / "ca.key").chmod(0o600)
    return Authority(name, directory / "ca.crt", directory / "ca.key")


def issue(
    authority: Authority, directory: Path, common_name: str, *, server: bool
) -> tuple[Path, Path]:
    """A certificate and key signed by `authority`, for a server on localhost or a client."""
    directory.mkdir(parents=True, exist_ok=True)
    _openssl(
        directory,
        *("req", "-newkey", "rsa:2048", "-nodes", "-subj", f"/CN={common_name}"),
        *("-keyout", "key.pem", "-out", "request.csr"),
    )
    usage = "serverAuth" if server else "clientAuth"
    extensions = f"extendedKeyUsage={usage}\n"
    if server:
        extensions += "subjectAltName=DNS:localhost,IP:127.0.0.1\n"
    with tempfile.NamedTemporaryFile("w", suffix=".ext") as file:
        file.write(extensions)
        file.flush()
        _openssl(
            directory,
            *("x509", "-req", "-in", "request.csr", "-days", DAYS),
            *("-CA", str(authority.certificate), "-CAkey", str(authority.key)),
            *("-CAcreateserial", "-out", "certificate.pem", "-extfile", file.name),
        )
    (directory / "key.pem").chmod(0o600)
    return directory / "certificate.pem", directory / "key.pem"

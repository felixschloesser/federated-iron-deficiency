"""Certificate authorities and certificates for the demo, made with openssl,
and the SuperNodes' key pairs, made with ssh-keygen.

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


def make_key_pair(path: Path) -> Path:
    """An ECDSA P-384 key pair, `path` and `path.pub` in OpenSSH format, as
    Flower's SuperNode authentication takes them; returns the private key."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ecdsa", "-b", "384", "-N", "", "-C", ""]
        + ["-f", str(path)],
        check=True,
        capture_output=True,
    )
    return path


def covers(certificate: Path, host: str) -> bool:
    """Whether `certificate` exists and names `host`, so a client checking the
    host accepts it; a certificate from before compose.yaml names localhost only."""
    if not certificate.exists():
        return False
    check = subprocess.run(
        ["openssl", "x509", "-in", str(certificate), "-noout", "-checkhost", host],
        capture_output=True,
        text=True,
        # Some openssl builds exit 1 when the host does not match: an answer, not an error.
        check=False,
    )
    return "does match" in check.stdout and "does NOT match" not in check.stdout


# The only names a browser should ever accept from a demo CA (RFC 5280 name
# constraints): trusting it then lends its key no power over real sites.
LOOPBACK = "permitted;DNS:localhost,permitted;IP:127.0.0.1/255.255.255.255"


def make_authority(
    directory: Path, name: str, *, loopback_only: bool = False
) -> Authority:
    """A self-signed certificate authority in `directory`; with `loopback_only`,
    one that may vouch only for localhost and 127.0.0.1."""
    directory.mkdir(parents=True, exist_ok=True)
    constraints = (
        ("-addext", f"nameConstraints=critical,{LOOPBACK}") if loopback_only else ()
    )
    _openssl(
        directory,
        *("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", DAYS),
        *("-subj", f"/CN={name} certificate authority"),
        # Stated, not left to the openssl build: strict verifiers require them.
        *("-addext", "basicConstraints=critical,CA:TRUE"),
        *("-addext", "keyUsage=critical,keyCertSign,cRLSign"),
        *constraints,
        *("-keyout", "ca.key", "-out", "ca.crt"),
    )
    # Owner only, whatever the openssl build's default.
    (directory / "ca.key").chmod(0o600)
    return Authority(name, directory / "ca.crt", directory / "ca.key")


def request(directory: Path, common_name: str) -> Path:
    """At the owner: its key pair, the private key kept in `directory` for the
    owner alone, and a request carrying the public key; returns the request."""
    directory.mkdir(parents=True, exist_ok=True)
    _openssl(
        directory,
        *("req", "-newkey", "rsa:2048", "-nodes", "-subj", f"/CN={common_name}"),
        *("-keyout", "key.pem", "-out", "request.csr"),
    )
    (directory / "key.pem").chmod(0o600)
    return directory / "request.csr"


def sign(authority: Authority, request_file: Path, *, server: bool) -> Path:
    """At the authority: a certificate for the request, beside it, for a server on
    localhost or a client. It reads the request alone, never a private key."""
    usage = "serverAuth" if server else "clientAuth"
    # Key identifiers and usage, as strict verifiers (Python 3.13, browsers) require.
    extensions = (
        f"extendedKeyUsage={usage}\n"
        "basicConstraints=CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "subjectKeyIdentifier=hash\n"
        "authorityKeyIdentifier=keyid,issuer\n"
    )
    if server:
        common_name = subject_name(request_file)
        # The common name is the server's host in compose.yaml; localhost for tests.
        extensions += f"subjectAltName=DNS:{common_name},DNS:localhost,IP:127.0.0.1\n"
    certificate = request_file.parent / "certificate.pem"
    with tempfile.NamedTemporaryFile("w", suffix=".ext") as file:
        file.write(extensions)
        file.flush()
        _openssl(
            request_file.parent,
            *("x509", "-req", "-in", request_file.name, "-days", DAYS),
            *("-CA", str(authority.certificate), "-CAkey", str(authority.key)),
            *("-CAcreateserial", "-out", certificate.name, "-extfile", file.name),
        )
    return certificate


def subject_name(request_file: Path) -> str:
    """The common name a request asks for."""
    result = subprocess.run(
        [
            "openssl",
            "req",
            "-in",
            str(request_file),
            "-noout",
            "-subject",
            "-nameopt",
            "multiline",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in result.stdout.splitlines():
        if line.strip().startswith("commonName"):
            return line.split("=", 1)[1].strip()
    raise ValueError(f"{request_file} names no common name")


def issue(
    authority: Authority, directory: Path, common_name: str, *, server: bool
) -> tuple[Path, Path]:
    """Request and sign in one go, for a party that is its own authority's: the
    SuperLink, a hospital's endpoint, a web app; its private key stays in
    `directory`."""
    certificate = sign(authority, request(directory, common_name), server=server)
    return certificate, directory / "key.pem"

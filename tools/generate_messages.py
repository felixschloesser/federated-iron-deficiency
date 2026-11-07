"""Generate the gRPC code and typed stubs of shared/messaging/messages.proto.

python tools/generate_messages.py            # into shared/messaging/
python tools/generate_messages.py --out DIR  # elsewhere (the drift test)
"""

import argparse
import re
import subprocess
import sys
from importlib import resources
from pathlib import Path

from grpc_tools import protoc

ROOT = Path(__file__).resolve().parents[1]
PROTO_DIR = ROOT / "shared" / "messaging"
GENERATED = (
    "messages_pb2.py",
    "messages_pb2.pyi",
    "messages_pb2_grpc.py",
    "messages_pb2_grpc.pyi",
)


def generate(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    status = protoc.main(
        [
            "protoc",
            f"--proto_path={PROTO_DIR}",
            # google/protobuf/timestamp.proto, as grpc_tools ships it.
            f"--proto_path={resources.files('grpc_tools') / '_proto'}",
            f"--python_out={out}",
            f"--grpc_python_out={out}",
            f"--mypy_out={out}",
            f"--mypy_grpc_out={out}",
            str(PROTO_DIR / "messages.proto"),
        ]
    )
    if status != 0:
        sys.exit(status)
    # protoc imports siblings as top-level modules; the package needs them relative.
    for name in ("messages_pb2_grpc.py", "messages_pb2_grpc.pyi"):
        module = out / name
        module.write_text(
            module.read_text().replace(
                "import messages_pb2 as", "from . import messages_pb2 as"
            )
        )
    # Importing timestamp_pb2 loads timestamp.proto, which messages.proto imports; the
    # generated module never names it again, so ruff's fix would drop the import.
    messages = out / "messages_pb2.py"
    messages.write_text(
        messages.read_text()
        + "\n_IMPORTED_PROTOS = (google_dot_protobuf_dot_timestamp__pb2,)\n"
    )
    # tidy's ruff fix turns mypy-protobuf's TypeAlias into a `type` statement, through
    # which mypy cannot reach an enum's ValueType: name the enum itself. No field
    # here shares an enum's name, which is what the Global___ alias guards against.
    stub = out / "messages_pb2.pyi"
    stub.write_text(
        re.sub(r"\bGlobal___(\w+)\.ValueType\b", r"\1.ValueType", stub.read_text())
    )
    tidy(out)


def tidy(out: Path) -> None:
    """Bring the generated code to the repository's ruff rules, so no gate excludes it.

    The unsafe fixes are type-alias syntax and version branches below Python 3.13.
    """
    ruff = str(Path(sys.executable).parent / "ruff")
    config = ["--config", str(ROOT / "pyproject.toml")]
    files = [str(out / name) for name in GENERATED]
    subprocess.run(
        [ruff, "check", *config, "--fix", "--unsafe-fixes", "--quiet", *files],
        check=True,
    )
    subprocess.run([ruff, "format", *config, "--quiet", *files], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=PROTO_DIR)
    generate(parser.parse_args().out)

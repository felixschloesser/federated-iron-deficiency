"""The committed gRPC code matches messages.proto (spec §10, R25)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = (
    "messages_pb2.py",
    "messages_pb2.pyi",
    "messages_pb2_grpc.py",
    "messages_pb2_grpc.pyi",
)


def test_generated_code_matches_the_proto(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "generate_messages.py"),
            "--out",
            str(tmp_path),
        ],
        check=True,
    )
    committed = ROOT / "web" / "messaging"
    for name in GENERATED:
        assert (tmp_path / name).read_text() == (committed / name).read_text(), name

"""What the startup's code can see and reach from inside a hospital."""

import os
import socket
from pathlib import Path

from flwr.app import ConfigRecord, Context, Message, RecordDict
from flwr.clientapp import ClientApp

app = ClientApp()

# Places a ClientApp has no business reaching: the hospital's staff app, and
# anywhere outside the deployment.
DESTINATIONS = ("{hospital}-web:8000", "pypi.org:443")


def visible_files(root: Path) -> list[str]:
    """Every file under `root` this process can list."""
    return sorted(
        str(Path(folder) / name) for folder, _, names in os.walk(root) for name in names
    )


def reachable(destination: str) -> bool:
    host, port = destination.rsplit(":", 1)
    try:
        with socket.create_connection((host, int(port)), timeout=3):
            return True
    except OSError:
        return False


@app.train()
def train(msg: Message, context: Context) -> Message:
    hospital = Path(str(context.node_config["data-path"])).parent
    destinations = [d.format(hospital=hospital.name) for d in DESTINATIONS]
    found = ConfigRecord(
        {
            "hospital": hospital.name,
            "files": visible_files(Path("/demo")) + visible_files(hospital),
            "reachable": [d for d in destinations if reachable(d)],
        }
    )
    return Message(content=RecordDict({"found": found}), reply_to=msg)

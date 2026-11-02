"""Logs what each hospital's probe ClientApp returned, one line per hospital."""

import json
from logging import INFO

from flwr.app import Context, Message, RecordDict
from flwr.serverapp import Grid, ServerApp
from flwr.supercore import log

app = ServerApp()


@app.main()
def main(grid: Grid, context: Context) -> None:
    replies = grid.send_and_receive(
        [
            Message(content=RecordDict(), dst_node_id=node, message_type="train")
            for node in grid.get_node_ids()
        ]
    )
    for reply in replies:
        if reply.has_error():
            log(INFO, "PROBE error %s", reply.error)
            continue
        found = reply.content.config_records["found"]
        report = {
            "hospital": found["hospital"],
            "files": sorted(set(found["files"])),
            "reachable": list(found["reachable"]),
        }
        log(INFO, "PROBE %s", json.dumps(report))

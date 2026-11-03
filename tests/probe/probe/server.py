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
        files, reachable = found["files"], found["reachable"]
        if not isinstance(files, list) or not isinstance(reachable, list):
            raise TypeError(
                "The probe ClientApp returns lists of files and destinations"
            )
        report = {
            "hospital": found["hospital"],
            "files": sorted({str(path) for path in files}),
            "reachable": [str(destination) for destination in reachable],
        }
        log(INFO, "PROBE %s", json.dumps(report))

"""Every test in this folder needs a running Docker engine: the folder is the
marker, so no test here can miss it."""

from pathlib import Path

import pytest

HERE = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if HERE in item.path.parents:
            item.add_marker(pytest.mark.containers)

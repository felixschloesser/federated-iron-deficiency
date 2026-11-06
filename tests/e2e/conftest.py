"""Every test in this folder runs the demo's containers: the folder marks them
`containers`, so none can miss the marker."""

from pathlib import Path

import pytest

HERE = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if HERE in item.path.parents:
            item.add_marker(pytest.mark.containers)

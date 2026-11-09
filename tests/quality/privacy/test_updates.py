"""What the startup receives of each hospital's training: the per-hospital
updates (the report's issue A: DD5, with L4 and I5 working on them)."""

import ast
from pathlib import Path

import pytest

ML = Path(__file__).resolve().parents[3] / "ml"


def names_in(module: str) -> set[str]:
    """Every name a module of ml/ uses or imports, read from its source:
    importing the apps would load Flower's CLI, whose Click deprecation warnings
    the test would report."""
    tree = ast.parse((ML / module).read_text(encoding="utf-8"))
    used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    return used | imported


@pytest.mark.privacy_issue
def test_the_startup_receives_no_hospital_update_in_plaintext() -> None:
    """Threat DD5 (issue A). Pass: the ClientApp masks its update with Flower's
    SecAgg+ mod and the ServerApp aggregates through SecAgg+, so the SuperLink
    and the ServerApp see only masked updates, whose sum is what averaging needs.
    It checks the code, not a run: it fails while either side lacks secure
    aggregation."""
    assert "secaggplus_mod" in names_in("client_app.py")
    assert "SecAggPlusWorkflow" in names_in("server_app.py")

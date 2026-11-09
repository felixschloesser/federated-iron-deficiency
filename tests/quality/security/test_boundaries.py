"""What each party's code may import, read from the source without running it.

Quality attribute: isolation of the parties. The runtime side, what each web app
installs, stores and serves, is in test_party_isolation.py. Each test's
docstring states its pass/fail measure."""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PARTIES = ("hospital", "practice", "startup")
# The parts of the Flower app any web code may import: the cohort's terms and
# the dataset's loaders.
SHARED_ML = {"ml.cohort", "ml.dataset"}
# The hospital also writes its training cohort and validates and runs the
# screening models it fetches; the startup only reads its own final models.
PARTY_ML = {
    "hospital": SHARED_ML
    | {"ml.final_model", "ml.inference", "ml.training_cohort", "ml.validation"},
    "practice": SHARED_ML,
    "startup": SHARED_ML | {"ml.final_model"},
}
ANALYSER_PORT = {"web.hospital.analyser", "web.hospital.analyser.port"}


def sources(*folders: str) -> Iterator[Path]:
    for folder in folders:
        yield from sorted((ROOT / folder).rglob("*.py"))


def imports(path: Path) -> Iterator[tuple[int, str]]:
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom):
            yield node.lineno, node.module or ""
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name


def party_of(parts: tuple[str, ...]) -> str | None:
    """The party whose folder holds a module (web/<party>/, tests/<party>/), by
    path parts or dotted name; None for shared code."""
    if len(parts) > 1 and parts[0] in {"web", "tests"} and parts[1] in PARTIES:
        return parts[1]
    return None


def test_no_party_imports_another_partys_code() -> None:
    """Pass: no module under web/<party>/ or tests/<party>/ imports another
    party's, and nothing under web/shared/ imports any party's."""
    found = []
    for path in sources("web", "tests"):
        rel = path.relative_to(ROOT)
        importer = party_of(rel.parts)
        # Tests outside the party folders may test every party.
        if importer is None and rel.parts[0] == "tests":
            continue
        for line, module in imports(path):
            imported = party_of(tuple(module.split(".")))
            if imported is not None and imported != importer:
                found.append(f"{rel}:{line}: imports {module}")
    assert found == []


@pytest.mark.parametrize("party", [*PARTIES, "shared"])
def test_web_code_imports_only_its_partys_part_of_the_flower_app(party: str) -> None:
    """Pass: web/<party>/ imports from ml/ only the modules PARTY_ML allows it
    (web/shared/ only SHARED_ML)."""
    allowed = PARTY_ML.get(party, SHARED_ML)
    found = [
        f"{path.relative_to(ROOT)}:{line}: imports {module}"
        for path in sources(f"web/{party}")
        for line, module in imports(path)
        if module.split(".")[0] == "ml" and module not in allowed
    ]
    assert found == []


def test_the_laboratory_reaches_the_analyser_only_through_its_port() -> None:
    """The analyser is an external system to the laboratory; the demo simulates
    it. Pass: no hospital module outside web/hospital/analyser/ imports anything
    of it but port.py."""
    found = [
        f"{path.relative_to(ROOT)}:{line}: imports {module}"
        for path in sources("web/hospital")
        if "analyser" not in path.relative_to(ROOT).parts
        for line, module in imports(path)
        if module.startswith("web.hospital.analyser") and module not in ANALYSER_PORT
    ]
    assert found == []


def assigned_list(tree: ast.Module, name: str) -> list[ast.expr]:
    """The elements of the list literal a module assigns to `name`."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if isinstance(value, ast.List) and any(
            isinstance(target, ast.Name) and target.id == name for target in targets
        ):
            return list(value.elts)
    return []


def settings_of(party: str) -> ast.Module:
    return ast.parse((ROOT / "web" / party / "settings.py").read_text())


def apps_in(party: str) -> set[str]:
    folder = ROOT / "web" / party
    return {
        ".".join(config.parent.relative_to(ROOT).parts)
        for config in [*folder.glob("apps.py"), *folder.glob("*/apps.py")]
    }


@pytest.mark.parametrize("party", PARTIES)
def test_a_party_installs_its_own_apps_and_no_other_partys(party: str) -> None:
    """Pass: web/<party>/settings.py installs every app in its folder and none in
    another party's."""
    installed = {
        element.value
        for element in assigned_list(settings_of(party), "INSTALLED_APPS")
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    }
    others = set().union(*(apps_in(other) for other in PARTIES if other != party))
    assert (apps_in(party) - installed, installed & others) == (set(), set())


def test_every_role_logs_in_to_exactly_one_party() -> None:
    """Pass: each member of Role is in the ROLES of one party's settings."""
    from web.shared.accounts.roles import Role

    holders: dict[str, list[str]] = {role.name: [] for role in Role}
    for party in PARTIES:
        for element in assigned_list(settings_of(party), "ROLES"):
            if isinstance(element, ast.Attribute):
                holders[element.attr].append(party)
    assert {role: held for role, held in holders.items() if len(held) != 1} == {}


def lines_of(*patterns: str) -> Iterator[tuple[str, int, str]]:
    for pattern in patterns:
        for path in sorted(ROOT.rglob(pattern)):
            rel = path.relative_to(ROOT)
            if any(part.startswith(".") for part in rel.parts):
                continue
            for number, line in enumerate(path.read_text().splitlines(), start=1):
                yield rel.as_posix(), number, line


# Split so that this file does not match its own patterns.
UNSAFE = ("|sa" + "fe", "mark" + "_safe(", "csrf" + "_exempt")
SUPPRESSIONS = ("# no" + "qa", "# type" + ": ignore", "filter" + "warnings")


def test_no_output_escapes_escaping_and_no_view_skips_csrf() -> None:
    """Pass: no template or module marks output safe or exempts a view from CSRF."""
    found = [
        f"{rel}:{number}: {marker}"
        for rel, number, line in lines_of("*.html", "*.py")
        for marker in UNSAFE
        if marker in line
    ]
    assert found == []


def test_no_warning_or_type_error_is_suppressed() -> None:
    """A suppressed warning hides the condition it warns of. Pass: no module or
    config file suppresses a lint, type or Python warning."""
    found = [
        f"{rel}:{number}: {marker}"
        for rel, number, line in lines_of("*.py", "*.toml", "*.cfg", "*.ini")
        for marker in SUPPRESSIONS
        if marker in line
    ]
    assert found == []

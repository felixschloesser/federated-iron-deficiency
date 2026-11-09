"""Repository audit: lists every rule violation, and fails on any.

Run `python .claude/audit.py` as a commit gate.
"""

import argparse
import ast
import re
import sys
import tomllib
from collections.abc import Callable, Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = Path(".claude") / "audit_allowlist.toml"
GLOSSARY = "glossary.toml"
# Rejected words and decision dates: the process's record, out of readers' way.
GLOSSARY_RECORD = Path(".claude/glossary_record.toml")
# Generated folders: collected static files (the demo's .demo/ is hidden).
BUILD_OUTPUT = {"staticfiles"}
# The parts of the training package any code under web/shared/ may import: the
# cohort's terms and the dataset's loaders (tests/quality/security/test_party_isolation.py).
SHARED_SIDE = {"ml.cohort", "ml.dataset"}
# What a party's code may import beyond: the hospital screens; the startup only
# reads its own final models, never screens.
TRAINING_SIDES = {
    # Also to write the training cohort its laboratory director provides.
    # Also to validate the screening models it fetches.
    "hospital": SHARED_SIDE
    | {"ml.final_model", "ml.inference", "ml.training_cohort", "ml.validation"},
    "startup": SHARED_SIDE | {"ml.final_model"},
}
# Settings modules that are no party's: what every party shares, and mypy's.
# The code every party shares; it has a settings.py too, the base of theirs.
SHARED = "shared"
# Every Django app lives under web/: one folder per party, and shared/.
WEB = Path("web")
ROLES_MODULE = WEB / SHARED / "accounts" / "roles.py"

# Split so that this file does not match its own patterns.
SUPPRESSIONS = (
    "# no" + "qa",
    "# type" + ": ignore",
    "csrf" + "_exempt",
    "filter" + "warnings",
)
SAFE_MARKERS = ("|sa" + "fe", "mark" + "_safe(")
MUTATORS = {
    "save",
    "create",
    "delete",
    "update",
    "bulk_create",
    "get_or_create",
    "update_or_create",
}
POST_HANDLERS = {"post", "form_valid", "put", "patch", "delete"}

TAG = re.compile(r"{%.*?%}|{{.*?}}")
CLASS_ATTR = re.compile(r'class="([^"]*)"')
CSS_CLASS = re.compile(r"\.([A-Za-z_][\w-]*)")


def files(root: Path, pattern: str) -> Iterator[Path]:
    """Yield matching files, skipping hidden folders (.venv, .git) and BUILD_OUTPUT."""
    for path in sorted(root.rglob(pattern)):
        parts = path.relative_to(root).parts
        if not any(part.startswith(".") or part in BUILD_OUTPUT for part in parts):
            yield path


def lines(root: Path, pattern: str) -> Iterator[tuple[str, int, str]]:
    for path in files(root, pattern):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            yield path.relative_to(root).as_posix(), number, line


def templates(root: Path) -> Iterator[Path]:
    return (path for path in files(root, "*.html") if "templates" in path.parts)


def css_classes(root: Path) -> list[str]:
    defined = {
        name
        for path in files(root, "*.css")
        if "static" in path.parts
        for name in CSS_CLASS.findall(path.read_text())
    }
    findings = []
    for path in templates(root):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            for value in CLASS_ATTR.findall(line):
                for name in TAG.sub(" ", value).split():
                    if name not in defined:
                        rel = path.relative_to(root).as_posix()
                        findings.append(
                            f"{rel}:{number}: class '{name}' is not defined in static/css"
                        )
    return findings


def includes_only(root: Path) -> list[str]:
    return [
        f"{path.relative_to(root).as_posix()}: page does not extend includes/base.html"
        for path in templates(root)
        if "includes" not in path.parts
        and not path.read_text().lstrip().startswith('{% extends "includes/')
    ]


def safe(root: Path) -> list[str]:
    allowlist_path = root / ALLOWLIST
    allowed = (
        tomllib.loads(allowlist_path.read_text()).get("safe", {})
        if allowlist_path.exists()
        else {}
    )
    candidates = [*lines(root, "*.html"), *lines(root, "*.py")]
    return [
        f"{rel}:{number}: unsafe output without an entry in {ALLOWLIST.as_posix()}"
        for rel, number, line in candidates
        if any(marker in line for marker in SAFE_MARKERS)
        and not str(allowed.get(rel, "")).strip()
    ]


def suppressions(root: Path) -> list[str]:
    candidates = [
        *lines(root, "*.py"),
        *lines(root, "*.toml"),
        *lines(root, "*.cfg"),
        *lines(root, "*.ini"),
    ]
    return [
        f"{rel}:{number}: suppression '{marker}'"
        for rel, number, line in candidates
        for marker in SUPPRESSIONS
        if marker in line
    ]


def _member_owner(node: ast.expr) -> str | None:
    """Return `Choice` for `Choice.MEMBER`, else None."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        owner = node.value.id
        if owner[:1].isupper() and node.attr.isupper():
            return owner
    return None


def listed_members(root: Path) -> list[str]:
    findings = []
    for path in files(root, "*.py"):
        # A party's settings list its roles; party_settings checks them instead.
        if path.relative_to(root).as_posix() in {
            f"web/{party}/settings.py" for party in parties(root)
        }:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
                elements: list[ast.expr | None] = list(node.elts)
            elif isinstance(node, ast.Dict):
                elements = list(node.keys)
            else:
                continue
            owners = {
                _member_owner(element) for element in elements if element is not None
            }
            if len(elements) >= 2 and len(owners) == 1 and None not in owners:
                rel = path.relative_to(root).as_posix()
                findings.append(
                    f"{rel}:{node.lineno}: members of {owners.pop()} listed; derive with match"
                )
    return findings


def _returns_response(function: ast.FunctionDef) -> bool:
    # mypy --strict annotates every function, so a view is one returning a response.
    returns = function.returns
    return returns is not None and ast.unparse(returns).endswith("Response")


def _is_atomic(decorator: ast.expr) -> bool:
    return ast.unparse(decorator) in {"transaction.atomic", "atomic"}


def writing_methods(root: Path) -> set[str]:
    """Model and manager methods that write: those under @transaction.atomic."""
    return {
        node.name
        for path in files(root, "models.py")
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.FunctionDef)
        and any(_is_atomic(decorator) for decorator in node.decorator_list)
    }


def _mutates(method: ast.FunctionDef, writers: set[str]) -> bool:
    """Whether a method saves, creates, deletes or updates, or calls a writing model
    or manager method."""
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and (node.func.attr in MUTATORS or node.func.attr in writers)
        for node in ast.walk(method)
    )


def get_mutation(root: Path) -> list[str]:
    """Views are classes, and only their POST handlers mutate."""
    findings = []
    writers = writing_methods(root)
    for path in files(root, "views.py"):
        rel = path.relative_to(root).as_posix()
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.FunctionDef) and _returns_response(node):
                findings.append(
                    f"{rel}:{node.lineno}: function view {node.name}; use a class-based view"
                )
            if not isinstance(node, ast.ClassDef) or not node.name.endswith("View"):
                continue
            for method in node.body:
                if (
                    isinstance(method, ast.FunctionDef)
                    and method.name not in POST_HANDLERS
                    and _mutates(method, writers)
                ):
                    findings.append(
                        f"{rel}:{method.lineno}: {node.name}.{method.name} mutates"
                        " outside a POST handler"
                    )
    return findings


def parties(root: Path) -> list[str]:
    """Each party: a folder at the top with a settings module of its own
    (web/<party>/settings.py)."""
    return sorted(
        path.parent.name
        for path in (root / WEB).glob("*/settings.py")
        if path.parent.name != SHARED
    )


def _owner(parts: tuple[str, ...], known: list[str]) -> str | None:
    """The party whose folder holds this module, at the top or under tests/, by
    path or dotted name; None for shared code."""
    if len(parts) > 1 and parts[0] in {"web", "tests"} and parts[1] in known:
        return parts[1]
    return None


def _web_imports(
    root: Path, folders: frozenset[str]
) -> Iterator[tuple[Path, int, str]]:
    """Each module imported by code under `folders`, with where."""
    for path in files(root, "*.py"):
        rel = path.relative_to(root)
        if rel.parts[0] not in folders:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            elif isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            else:
                continue
            for module in modules:
                yield rel, node.lineno, module


def training_imports(root: Path) -> list[str]:
    """Web code imports only the parts of the training package its party may
    (tests/quality/security/test_party_isolation.py)."""
    known = parties(root)
    findings = []
    for rel, line, module in _web_imports(root, frozenset({"web"})):
        party = _owner(rel.parts, known)
        allowed = TRAINING_SIDES.get(party or "", SHARED_SIDE)
        if module.split(".")[0] != "ml" or module in allowed:
            continue
        readers = [
            name for name in known if module in TRAINING_SIDES.get(name, SHARED_SIDE)
        ]
        who = " or ".join(f"the {name}'s" for name in readers)
        findings.append(
            f"{rel.as_posix()}:{line}: imports {module}, "
            + (f"{who} code" if readers else "the Flower app's code")
        )
    return findings


def party_imports(root: Path) -> list[str]:
    """A party's apps and tests never import another party's; shared code imports
    none (tests/quality/security/test_party_isolation.py)."""
    known = parties(root)
    findings = []
    for rel, line, module in _web_imports(root, frozenset({"web", "tests"})):
        imported = _owner(tuple(module.split(".")), known)
        importer = _owner(rel.parts, known)
        # Shared tests may still test every party; a party's tests only its own.
        shared_test = importer is None and rel.parts[0] == "tests"
        if imported is None or imported == importer or shared_test:
            continue
        who = f"the {importer}'s code" if importer else "shared code"
        parts = module.split(".")
        package = ".".join(parts[:2])
        findings.append(f"{rel.as_posix()}:{line}: {who} imports {package}")
    return findings


# The analyser is an external system to the laboratory (glossary.toml); the
# hospital's code knows it only through its port.
ANALYSER = ("web", "hospital", "analyser")
ANALYSER_PORT = {"web.hospital.analyser", "web.hospital.analyser.port"}


def analyser_port(root: Path) -> list[str]:
    """The hospital's code reaches the analyser only through
    web/hospital/analyser/port.py; only the analyser's own code uses its models."""
    return [
        f"{rel.as_posix()}:{line}: imports {module}; use web.hospital.analyser.port"
        for rel, line, module in _web_imports(root, frozenset({"web"}))
        if rel.parts[1:2] == ("hospital",)
        if module.startswith("web.hospital.analyser")
        and module not in ANALYSER_PORT
        and rel.parts[:3] != ANALYSER
    ]


def _assigned_list(tree: ast.Module, name: str) -> list[ast.expr]:
    """The elements of the list literal assigned to `name` at module level, with
    or without an annotation."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        named = any(
            isinstance(target, ast.Name) and target.id == name for target in targets
        )
        if named and isinstance(value, ast.List):
            return list(value.elts)
    return []


def _party_apps(root: Path, party: str) -> set[str]:
    """The Django apps in the party's folder, by module name."""
    folder = root / WEB / party
    return {
        ".".join(config.parent.relative_to(root).parts)
        for config in [*folder.glob("apps.py"), *folder.glob("*/apps.py")]
    }


def party_settings(root: Path) -> list[str]:
    """Each party's settings install the apps in its own folder and no other
    party's, and every role logs in to exactly one party's web app: the lists a
    party's settings write out (.claude/CLAUDE.md), checked against the folders
    and the Role class."""
    known = parties(root)
    findings = []
    holders: dict[str, list[str]] = {}
    for party in known:
        rel = f"web/{party}/settings.py"
        tree = ast.parse((root / rel).read_text())
        installed = {
            element.value
            for element in _assigned_list(tree, "INSTALLED_APPS")
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }
        findings += [
            f"{rel}: does not install {app}"
            for app in sorted(_party_apps(root, party) - installed)
        ]
        findings += [
            f"{rel}: installs {app}, the {other}'s"
            for other in known
            if other != party
            for app in sorted(_party_apps(root, other) & installed)
        ]
        for element in _assigned_list(tree, "ROLES"):
            if isinstance(element, ast.Attribute):
                holders.setdefault(element.attr, []).append(party)
    roles_path = root / ROLES_MODULE
    if roles_path.exists():
        roles = [
            target.id
            for node in ast.walk(ast.parse(roles_path.read_text()))
            if isinstance(node, ast.ClassDef) and node.name == "Role"
            for statement in node.body
            if isinstance(statement, ast.Assign)
            for target in statement.targets
            if isinstance(target, ast.Name)
        ]
        for role in roles:
            held = holders.get(role, [])
            if len(held) != 1:
                where = " and ".join(held) if held else "no party"
                findings.append(
                    f"{ROLES_MODULE.as_posix()}: Role.{role} logs in to {where}"
                )
    return findings


def glossary_entries(root: Path) -> list[str]:
    """Each party's words are in its folder's glossary.toml, the words they share
    in web/shared/glossary.toml, and nowhere else; every term has a source and a
    meaning; the process's record of rejected words names only glossary terms."""
    known = {*parties(root), SHARED}
    findings = []
    entries: dict[str, dict[str, object]] = {}
    for path in sorted((root / WEB).glob(f"*/{GLOSSARY}")):
        rel = path.relative_to(root).as_posix()
        if path.parent.name not in known:
            findings.append(f"{rel}: neither a party's glossary nor the shared one")
            continue
        for term, entry in tomllib.loads(path.read_text()).items():
            entries[term] = entry
            source = str(entry.get("source", "")).strip()
            if source in ("", "—", "-") or "unsourced" in source.lower():
                findings.append(f"{rel}: term '{term}' has no source")
            elif not str(entry.get("meaning", "")).strip():
                findings.append(f"{rel}: term '{term}' has no meaning")
    record = root / GLOSSARY_RECORD
    if record.exists():
        findings += [
            f"{GLOSSARY_RECORD.as_posix()}: term '{term}' is in no glossary"
            for term in tomllib.loads(record.read_text())
            if term not in entries
        ]
    return findings


# "glossary.toml" with no folder before it: web/<party>/ or web/shared/.
UNPLACED_GLOSSARY = re.compile(r"(?<![a-z]/)glossary\.toml")


def glossary_citations(root: Path) -> list[str]:
    """Code that cites a glossary names which: each party has its own
    (web/<party>/glossary.toml), the shared words are in web/shared/."""
    return [
        f"{rel}:{number}: cites glossary.toml without its folder"
        for pattern in ("*.py", "*.html")
        for rel, number, line in lines(root, pattern)
        if rel.startswith(("web/", "tests/", "demo/", "ml/"))
        and UNPLACED_GLOSSARY.search(line)
    ]


FEATURE_FILE = re.compile(r"features/[a-z_/]+\.feature")


def _docstring_lines(tree: ast.Module) -> list[range]:
    """The lines of each module and class docstring."""
    found = []
    for node in [tree, *ast.walk(tree)]:
        if not isinstance(node, (ast.Module, ast.ClassDef)) or not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            found.append(range(first.lineno, (first.end_lineno or 0) + 1))
    return found


def feature_citations(root: Path) -> list[str]:
    """Outside tests/, a feature file is named only in a module or class
    docstring, once in each."""
    findings = []
    for path in files(root, "*.py"):
        name = path.relative_to(root).as_posix()
        if name.startswith("tests/"):
            continue
        text = path.read_text()
        docstrings = _docstring_lines(ast.parse(text))
        cited: set[range] = set()
        for number, line in enumerate(text.splitlines(), start=1):
            for _ in FEATURE_FILE.finditer(line):
                home = next((lines for lines in docstrings if number in lines), None)
                if home is None:
                    findings.append(
                        f"{name}:{number}: feature file named outside a module or"
                        " class docstring"
                    )
                elif home in cited:
                    findings.append(
                        f"{name}:{number}: a second feature file in one docstring"
                    )
                else:
                    cited.add(home)
    return findings


CHECKS: dict[str, Callable[[Path], list[str]]] = {
    check.__name__: check
    for check in (
        css_classes,
        includes_only,
        safe,
        suppressions,
        listed_members,
        get_mutation,
        glossary_entries,
        glossary_citations,
        feature_citations,
        training_imports,
        party_imports,
        party_settings,
        analyser_port,
    )
}


def run(root: Path) -> dict[str, list[str]]:
    return {name: check(root) for name, check in CHECKS.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    findings = run(args.root)
    for name, found in findings.items():
        if found:
            print(f"{name}: {len(found)}")
            for finding in found:
                print(f"  {finding}")
    if any(findings.values()):
        return 1
    print("audit: no findings (" + ", ".join(findings) + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())

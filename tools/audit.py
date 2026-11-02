"""Repository audit: counts rule violations against a baseline that only goes down.

Run `python tools/audit.py` as a commit gate; `--update` lowers the baseline
after a fix and refuses to raise it.
"""

import argparse
import ast
import json
import re
import sys
import tomllib
from collections.abc import Callable, Iterator
from pathlib import Path

from web.party import Party

ROOT = Path(__file__).resolve().parents[1]
BASELINE = Path("tools") / "audit_baseline.json"
ALLOWLIST = Path("tools") / "audit_allowlist.toml"
SPEC = Path("docs") / "spec" / "requirements.md"
# Generated folders: collected static files, and the demo deployment (tools/demo.py).
BUILD_OUTPUT = {"staticfiles", "demo"}
# The parts of the training package a hospital's web app may import (R21);
# everything else under web/ only the dataset's terms and loaders.
HOSPITAL_SIDE = {"iron_deficiency.screening", "iron_deficiency.dataset"}
SHARED_SIDE = {"iron_deficiency.dataset"}

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


def kit_only(root: Path) -> list[str]:
    return [
        f"{path.relative_to(root).as_posix()}: page does not extend the kit"
        for path in templates(root)
        if "kit" not in path.parts
        and not path.read_text().lstrip().startswith('{% extends "kit/')
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
    """Whether a method saves, creates, deletes or updates, or calls a service or a
    writing model method."""
    for node in ast.walk(method):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            chain = node.func
            while isinstance(chain.value, ast.Attribute):
                chain = chain.value
            if (
                node.func.attr in MUTATORS
                or node.func.attr in writers
                or (isinstance(chain.value, ast.Name) and chain.value.id == "services")
            ):
                return True
    return False


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


def _web_imports(root: Path) -> Iterator[tuple[Path, int, str]]:
    """Each module imported by code under web/, with where."""
    for path in files(root, "*.py"):
        rel = path.relative_to(root)
        if rel.parts[0] != "web":
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
    """Hospital software uses only the screening side of the training package,
    the rest of web/ only the dataset (R21)."""
    hospital = set(Party.HOSPITAL.apps())
    findings = []
    for rel, line, module in _web_imports(root):
        if module.split(".")[0] != "iron_deficiency":
            continue
        if module not in HOSPITAL_SIDE:
            findings.append(f"{rel.as_posix()}:{line}: imports {module}, startup code")
        elif ".".join(rel.parts[:2]) not in hospital and module not in SHARED_SIDE:
            findings.append(
                f"{rel.as_posix()}:{line}: imports {module}, the hospital's code"
            )
    return findings


def party_imports(root: Path) -> list[str]:
    """A party's apps never import the other party's; shared code imports neither (R21)."""
    owner = {app: party for party in Party for app in party.apps()}
    findings = []
    for rel, line, module in _web_imports(root):
        app = ".".join(module.split(".")[:2])
        imported = owner.get(app)
        importer = owner.get(".".join(rel.parts[:2]))
        if imported is None or imported is importer:
            continue
        who = f"the {importer.value}'s code" if importer else "shared code"
        findings.append(f"{rel.as_posix()}:{line}: {who} imports {app}")
    return findings


def glossary_sources(root: Path) -> list[str]:
    path = root / SPEC
    if not path.exists():
        return []
    vocabulary = path.read_text().split("Vocabulary", 1)[-1].split("\n## ", 1)[0]
    findings = []
    for row in vocabulary.splitlines():
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        if (
            not row.startswith("|")
            or len(cells) < 2
            or cells[0] == "Term"
            or cells[0].startswith("---")
        ):
            continue
        source = cells[1]
        if source in ("", "—", "-") or "unsourced" in source.lower():
            findings.append(f"{SPEC.as_posix()}: term '{cells[0]}' has no source")
    return findings


CHECKS: dict[str, Callable[[Path], list[str]]] = {
    check.__name__: check
    for check in (
        css_classes,
        kit_only,
        safe,
        suppressions,
        listed_members,
        get_mutation,
        glossary_sources,
        training_imports,
        party_imports,
    )
}


def run(root: Path) -> dict[str, list[str]]:
    return {name: check(root) for name, check in CHECKS.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--update", action="store_true", help="lower the baseline")
    args = parser.parse_args(argv)

    baseline_path = args.root / BASELINE
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
    findings = run(args.root)
    counts = {name: len(found) for name, found in findings.items()}
    increased = [
        name for name, count in counts.items() if count > baseline.get(name, 0)
    ]

    for name in increased:
        print(f"{name}: {counts[name]} (baseline {baseline.get(name, 0)})")
        for finding in findings[name]:
            print(f"  {finding}")
    if increased:
        return 1
    if args.update:
        baseline_path.write_text(json.dumps(counts, indent=2, sort_keys=True) + "\n")
    print("audit: " + ", ".join(f"{name} {count}" for name, count in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())

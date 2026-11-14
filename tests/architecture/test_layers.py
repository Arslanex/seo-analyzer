"""Architecture rules, checked from the source (no imports are executed).

Layers, innermost first: ``domain`` < ``application`` < ``infrastructure`` < ``presentation``.
A module may import its own layer and any layer to its left; never one to its right.
``seoa.config`` (settings) and ``seoa.bootstrap`` (composition root) sit outside the layers.

Imports under ``if TYPE_CHECKING:`` are annotations only and do not count.
``KNOWN_DEBT`` lists the inward-pointing imports that still violate the rule. Each entry says
why it exists; the list may only shrink (a stale entry fails the test).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
PKG = "seoa"
LAYERS = ["domain", "application", "infrastructure", "presentation"]
OUTSIDE = {"seoa.config", "seoa.bootstrap"}

# (importer, imported) -> reason. Keep this list short and shrinking.
KNOWN_DEBT: dict[tuple[str, str], str] = {}


def _modules() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for path in (SRC / PKG).rglob("*.py"):
        parts = list(path.relative_to(SRC).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        out[".".join(parts)] = path
    return out


def _layer(module: str) -> str | None:
    if module in OUTSIDE or not module.startswith(PKG + "."):
        return None
    parts = module.split(".")
    return parts[1] if len(parts) > 1 and parts[1] in LAYERS else None


def _runtime_imports(path: Path, module: str, known: set[str]) -> set[str]:
    """Absolute ``seoa.*`` modules imported at runtime (TYPE_CHECKING blocks are skipped)."""
    tree = ast.parse(path.read_text())
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
            skip.update(id(n) for n in ast.walk(node))
    found: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"{module}: use absolute imports"
            if node.module and node.module.startswith(PKG):
                submodules = {f"{node.module}.{a.name}" for a in node.names} & known
                found.update(submodules)  # ``from pkg import submodule`` depends on the submodule
                if len(submodules) < len(node.names):  # ... and names taken from ``pkg`` itself
                    found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(a.name for a in node.names if a.name.startswith(PKG))
    return found


def _edges() -> dict[str, set[str]]:
    mods = _modules()
    graph: dict[str, set[str]] = {}
    for module, path in mods.items():
        graph[module] = {i for i in _runtime_imports(path, module, set(mods)) if i != module}
    return graph


def _violations() -> set[tuple[str, str]]:
    bad: set[tuple[str, str]] = set()
    for importer, targets in _edges().items():
        src_layer = _layer(importer)
        if src_layer is None:
            continue
        for target in targets:
            dst_layer = _layer(target)
            if dst_layer and LAYERS.index(dst_layer) > LAYERS.index(src_layer):
                bad.add((importer, target))
    return bad


def test_inner_layers_never_import_outer_layers() -> None:
    new = sorted(v for v in _violations() if v not in KNOWN_DEBT)
    assert not new, "inward-pointing imports only:\n" + "\n".join(f"  {a} -> {b}" for a, b in new)


def test_known_debt_has_no_stale_entries() -> None:
    stale = sorted(set(KNOWN_DEBT) - _violations())
    assert not stale, f"remove from KNOWN_DEBT (fixed): {stale}"


def test_domain_depends_on_nothing_else_in_the_project() -> None:
    for importer, targets in _edges().items():
        if _layer(importer) != "domain":
            continue
        for target in targets:
            assert _layer(target) == "domain", f"{importer} -> {target}"


def test_infrastructure_does_not_know_presentation() -> None:
    for importer, targets in _edges().items():
        if _layer(importer) == "infrastructure":
            assert not [t for t in targets if _layer(t) == "presentation"], importer


def test_nothing_but_entry_points_imports_the_composition_root() -> None:
    importers = [m for m, t in _edges().items() if "seoa.bootstrap" in t]
    assert importers == [], importers


def test_there_are_no_import_cycles_between_modules() -> None:
    graph = _edges()
    state: dict[str, int] = {}
    cycle: list[str] = []

    def visit(node: str, stack: list[str]) -> bool:
        state[node] = 1
        stack.append(node)
        for nxt in sorted(graph.get(node, ())):
            if state.get(nxt) == 1:
                cycle.extend(stack[stack.index(nxt) :] + [nxt])
                return True
            if nxt not in state and visit(nxt, stack):
                return True
        stack.pop()
        state[node] = 2
        return False

    for module in sorted(graph):
        if module not in state and visit(module, []):
            break
    assert not cycle, "import cycle: " + " -> ".join(cycle)


def test_every_module_belongs_to_a_layer_or_is_outside_them() -> None:
    stray = sorted(m for m in _modules() if m != PKG and _layer(m) is None and m not in OUTSIDE)
    assert not stray, stray


@pytest.mark.parametrize("layer", LAYERS)
def test_each_layer_package_has_a_docstring(layer: str) -> None:
    init = SRC / PKG / layer / "__init__.py"
    assert init.exists() and ast.get_docstring(ast.parse(init.read_text())), init

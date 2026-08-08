"""The execution contract — how `ent` obtains and calls a node (Phase 7 §1).

A node is executed through `contract.entrypoint: <module path>::<callable>`. The
callable takes one argument (the input dict) and returns the output dict. The
module path must be one of the node's `claims` (validated in validation.py).

Cross-check with `@ent.node()`: if the resolved callable is decorated for a
*different* node id, that is drift — reported like the extractor reports edge
drift. And for a node that has a decorated callable but no `entrypoint`, the
extractor proposes the line so filling it in is copy-paste, not archaeology.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from typing import Callable


class EntrypointError(RuntimeError):
    """Base: the node's runnable entrypoint could not be resolved."""


class NoEntrypoint(EntrypointError):
    """The node declares no contract.entrypoint (⇒ UNTESTED)."""


class EntrypointDrift(EntrypointError):
    """contract.entrypoint and @ent.node() disagree about which node this is."""


def entrypoint_spec(node: "object") -> str | None:
    return (getattr(node, "raw", {}) or {}).get("contract", {}).get("entrypoint")  # type: ignore[attr-defined]


def harness_spec(node: "object") -> str | None:
    return (getattr(node, "raw", {}) or {}).get("contract", {}).get("harness")  # type: ignore[attr-defined]


class Harness:
    """What a harness is handed: the resolved entrypoint, the project root, and
    the node itself. Everything a fixture row cannot express in JSON."""

    __slots__ = ("entrypoint", "root", "node")

    def __init__(self, entrypoint: Callable[..., object], root: Path, node: "object") -> None:
        self.entrypoint = entrypoint
        self.root = Path(root)
        self.node = node


def resolve_harness(node: "object", root: Path) -> Callable[..., object] | None:
    """Import the node's harness callable, or None if it declares no harness.

    The harness is the seam for units whose entrypoint is not a one-argument
    function — `f(node, root)`, `f(root, node_id)`, a class that must be
    constructed first. Without it such units are permanently UNTESTED, which
    is a hole in the map, not a fact about the code.

    It lives with the fixtures rather than in the node's claims: it is test
    scaffolding, so editing it must not move the composite fingerprint.
    """
    spec = harness_spec(node)
    if not spec:
        return None

    rel_path, sep, callable_name = spec.partition("::")
    if not sep or not callable_name:
        raise EntrypointError(f"harness '{spec}' must be '<path>::<callable>'")
    path = Path(root) / rel_path
    if not path.exists():
        raise EntrypointError(f"harness file '{rel_path}' does not exist")

    module = _import_file(path, f"{getattr(node, 'id', 'node')}::harness", Path(root))
    fn = getattr(module, callable_name, None)
    if fn is None or not callable(fn):
        raise EntrypointError(f"'{callable_name}' is not a callable in {rel_path}")
    return fn


def resolve_entrypoint(node: "object", root: Path) -> Callable[..., object]:
    """Import and return the node's entrypoint callable.

    Raises NoEntrypoint if none is declared, EntrypointDrift on decorator
    mismatch, EntrypointError on import/attribute failure.
    """
    spec = entrypoint_spec(node)
    if not spec:
        raise NoEntrypoint(f"{node.id}: no contract.entrypoint")  # type: ignore[attr-defined]

    rel_path, sep, callable_name = spec.partition("::")
    if not sep or not callable_name:
        raise EntrypointError(f"entrypoint '{spec}' must be '<path>::<callable>'")

    path = Path(root) / rel_path
    if not path.exists():
        raise EntrypointError(f"entrypoint file '{rel_path}' does not exist")

    module = _import_file(path, node.id, Path(root))  # type: ignore[attr-defined]
    fn = getattr(module, callable_name, None)
    if fn is None or not callable(fn):
        raise EntrypointError(f"'{callable_name}' is not a callable in {rel_path}")

    decorated_id = getattr(fn, "__entiendo_node_id__", None)
    if decorated_id is not None and decorated_id != node.id:  # type: ignore[attr-defined]
        raise EntrypointDrift(
            f"{node.id}: entrypoint '{spec}' is @ent.node('{decorated_id}') — "  # type: ignore[attr-defined]
            "the decorator and the manifest disagree"
        )
    return fn


def _package_context(path: Path) -> tuple[Path, str] | None:
    """(sys.path entry, dotted module name) if `path` lives inside a Python
    package, else None.

    A module inside a package uses relative imports (`from .exc import ...`),
    which only resolve when it is imported under its REAL dotted name. Loading
    it as a standalone file raises "attempted relative import with no known
    parent package" — which blocked tier0 on essentially every packaged
    library. Walk up while __init__.py exists; the first directory without one
    is the import root.
    """
    if path.suffix != ".py" or not (path.parent / "__init__.py").exists():
        return None
    parts = [path.stem]
    d = path.parent
    while (d / "__init__.py").exists():
        parts.append(d.name)
        d = d.parent
        if d == d.parent:                        # filesystem root — give up
            return None
    return d, ".".join(reversed(parts))


def _purge(dotted: str) -> None:
    """Drop the module and its whole top-level package from sys.modules so each
    eval re-executes the CURRENT file — a cached module would report health for
    code that is no longer on disk (`ent dev` re-evaluates in one process)."""
    top = dotted.split(".")[0]
    for name in [m for m in sys.modules
                 if m == top or m.startswith(top + ".")]:
        sys.modules.pop(name, None)


def _import_file(path: Path, node_id: str, root: Path):
    pkg = _package_context(path)
    if pkg is not None:
        pkg_root, dotted = pkg
        pkg_str = str(pkg_root.resolve())
        added_pkg = pkg_str not in sys.path
        if added_pkg:
            sys.path.insert(0, pkg_str)
        try:
            _purge(dotted)
            return importlib.import_module(dotted)
        except Exception as exc:                 # import-time failure = ERROR
            raise EntrypointError(f"could not import {dotted}: {exc}")
        finally:
            if added_pkg and pkg_str in sys.path:
                sys.path.remove(pkg_str)

    mod_name = "ent_node_" + node_id.replace(".", "_").replace("-", "_")
    root_str = str(root.resolve())
    added = root_str not in sys.path
    if added:
        sys.path.insert(0, root_str)
    try:
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            raise EntrypointError(f"could not load {path}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # import-time failure is a harness ERROR
            raise EntrypointError(f"could not import {path.name}: {exc}")
    finally:
        if added and root_str in sys.path:
            sys.path.remove(root_str)
    return module


# --------------------------------------------------------------------------- #
# static scan — propose entrypoints / detect drift without executing
# --------------------------------------------------------------------------- #

def scan_decorated(path: Path) -> dict[str, str]:
    """Map function name → node id for every `@ent.node("id")` in a .py file.

    Pure AST — never imports or runs the module.
    """
    out: dict[str, str] = {}
    try:
        tree = ast.parse(Path(path).read_text())
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return out
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            node_id = _node_id_from_decorator(dec)
            if node_id is not None:
                out[node.name] = node_id
    return out


def _node_id_from_decorator(dec: ast.AST) -> str | None:
    # matches @ent.node("id") / @node("id")
    if not isinstance(dec, ast.Call):
        return None
    func = dec.func
    is_node = (isinstance(func, ast.Attribute) and func.attr == "node") or (
        isinstance(func, ast.Name) and func.id == "node"
    )
    if is_node and dec.args and isinstance(dec.args[0], ast.Constant):
        return dec.args[0].value
    return None


def propose_entrypoint(node: "object", root: Path) -> str | None:
    """Suggest a `contract.entrypoint` for a node that has a decorated callable
    in its claims but no entrypoint declared. Returns '<path>::<func>' or None."""
    if entrypoint_spec(node):
        return None
    for claim in getattr(node, "claims", ()):  # type: ignore[attr-defined]
        path = Path(root) / claim
        if path.suffix != ".py" or not path.exists():
            continue
        for func_name, node_id in scan_decorated(path).items():
            if node_id == node.id:  # type: ignore[attr-defined]
                return f"{claim}::{func_name}"
    return None

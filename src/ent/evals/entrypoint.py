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


def _import_file(path: Path, node_id: str, root: Path):
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

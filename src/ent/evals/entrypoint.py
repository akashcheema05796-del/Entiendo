"""Resolve a node's runnable entrypoint from its claimed files.

tier1/tier2 need to *execute* the node (tier0 stays static). The entrypoint is
the `@ent.node("<id>")`-decorated callable in one of the node's claimed .py
files — the decorator stamps `__entiendo_node_id__`, so we import each claimed
module and look for the matching callable.

Importing is best-effort and isolated: the project root is put on `sys.path` so a
node's absolute intra-project imports resolve. A node whose code can't be imported
in isolation (e.g. relative imports with no package context, missing runtime deps)
raises EntrypointError, and the callers degrade to a clear "not runnable" skip
rather than failing the whole eval.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Callable


class EntrypointError(RuntimeError):
    """The node's runnable entrypoint could not be resolved."""


def resolve_entrypoint(node: "object", root: Path) -> Callable[..., object]:
    root = Path(root)
    errors: list[str] = []
    for claim in getattr(node, "claims", ()):  # type: ignore[attr-defined]
        path = root / claim
        if path.suffix != ".py" or not path.exists():
            continue
        try:
            fn = _load_and_find(path, node.id, root)  # type: ignore[attr-defined]
        except Exception as exc:  # import-time failure
            errors.append(f"{claim}: {exc}")
            continue
        if fn is not None:
            return fn
    if errors:
        raise EntrypointError("; ".join(errors))
    raise EntrypointError(
        f"no @ent.node('{node.id}') callable found in claimed .py files"  # type: ignore[attr-defined]
    )


def _load_and_find(path: Path, node_id: str, root: Path) -> Callable[..., object] | None:
    mod_name = "ent_node_" + node_id.replace(".", "_").replace("-", "_")
    root_str = str(root.resolve())
    added = root_str not in sys.path
    if added:
        sys.path.insert(0, root_str)
    try:
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if added and root_str in sys.path:
            sys.path.remove(root_str)

    for value in vars(module).values():
        if callable(value) and getattr(value, "__entiendo_node_id__", None) == node_id:
            return value
    return None

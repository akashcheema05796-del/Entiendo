"""Python import extraction — the reference `LanguageExtractor`.

This is the original reconciler logic, unchanged in behaviour, moved behind the
seam: parse the AST, walk `import` / `from … import`, and resolve each to an
intra-project `.py` file (or package `__init__.py`), handling relative-import
depth. Third-party packages don't resolve to a project file and are dropped.
"""

from __future__ import annotations

import ast
from pathlib import Path

from .base import ImportEdge


class PythonExtractor:
    name = "python"
    extensions = (".py",)

    def resolved_imports(self, file: Path, root: Path) -> list[ImportEdge]:
        try:
            tree = ast.parse(file.read_text())
        except (SyntaxError, UnicodeDecodeError, ValueError):
            return []
        out: list[ImportEdge] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._add(out, alias.name, 0, file, root)
            elif isinstance(node, ast.ImportFrom):
                self._add(out, node.module or "", node.level, file, root)
        return out

    def _add(self, out: list[ImportEdge], module: str, level: int,
             importing: Path, root: Path) -> None:
        target = _resolve(module, level, importing, root)
        if target is not None:
            out.append(ImportEdge(target=target, detail=module or "."))


def _resolve(module: str, level: int, importing: Path, root: Path) -> Path | None:
    """Resolve a Python import to a project file, or None if external.

    `level` is the relative-import depth (0 = absolute / root-relative).
    """
    if level > 0:
        base = importing.parent
        for _ in range(level - 1):
            base = base.parent
    else:
        base = root
    parts = module.split(".") if module else []
    target = base.joinpath(*parts)
    for candidate in (target.with_suffix(".py"), target / "__init__.py"):
        if candidate.exists():
            return candidate.resolve()
    return None

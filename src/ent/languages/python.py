"""Python import extraction — the reference `LanguageExtractor`.

Parse the AST, walk `import` / `from … import`, and resolve each to an
intra-project `.py` file (or package `__init__.py`), handling relative-import
depth. Third-party packages don't resolve to a project file and are dropped.

Resolution tries three roots, in order (astrobee gap 3 — the map had ZERO
edges on a 43-unit catkin repo because every cross-package import is by
installed name, invisible from the repo root):

  1. the repo root (the original behaviour) — `import lib.maths`;
  2. the importing file's own directory — a script run as a script has its
     dir on sys.path, so `import sibling_module` between scripts is real;
  3. the repo-wide package map: any directory whose parent has no
     __init__.py but which has one itself is an importable top-level
     package wherever it lives (`localization/…/scripts/localization_common`
     → `import localization_common`). Same-named packages in different
     places are AMBIGUOUS and refused — a guessed edge is worse than a
     declared blind spot.
"""

from __future__ import annotations

import ast
from pathlib import Path

from .base import AdapterCapabilities, ImportEdge


class PythonExtractor:
    name = "python"
    extensions = (".py",)

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            grade="ast",
            evidenceTag="import",
            cannotResolve=(
                "importlib.import_module / __import__ with runtime arguments "
                "(flagged as possibleUndeclaredDynamicDep, not resolved to edges)",
                "getattr / string-keyed dispatch onto modules",
                "subprocess-spawned interpreters and os.system calls",
                "network calls (requests/httpx/urllib) — out-of-process by nature",
                "same-named top-level packages in different directories "
                "(ambiguous — refused, never guessed)",
            ))

    def resolved_imports(self, file: Path, root: Path) -> list[ImportEdge]:
        try:
            tree = ast.parse(file.read_text())
        except (SyntaxError, UnicodeDecodeError, ValueError, OSError):
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
    found = _try_module(base, parts)
    if found is not None:
        return found
    if level == 0 and parts:
        # script-style sibling: a file run as a script has its own directory
        # on sys.path, so `import sibling` between scripts in one dir is real
        found = _try_module(importing.parent, parts)
        if found is not None:
            return found
        # top-level package rooted deeper in the tree (catkin / src layouts)
        pkg_dir = _package_map(root).get(parts[0])
        if pkg_dir is not None:
            if len(parts) == 1:
                return (pkg_dir / "__init__.py").resolve()
            return _try_module(pkg_dir, parts[1:])
    return None


def _try_module(base: Path, parts: list[str]) -> Path | None:
    target = base.joinpath(*parts)
    for candidate in (target.with_suffix(".py"), target / "__init__.py"):
        try:
            if candidate.exists():
                return candidate.resolve()
        except OSError:
            continue                     # unstat-able garbage — not a module
    return None


# --------------------------------------------------------------------------- #
# repo-wide package map — by-name imports in monorepos (astrobee gap 3)
# --------------------------------------------------------------------------- #

_PKG_CACHE: dict[str, dict[str, Path | None]] = {}


def _package_map(root: Path) -> dict[str, Path | None]:
    """Top-level package name → package dir, cached per root.

    A directory with an `__init__.py` whose PARENT has none is an importable
    top-level package wherever it sits (its parent joins sys.path via setup.py,
    catkin, or a script's own dir). Without this map, every `import X` between
    such packages is invisible — the worst kind of missing edge, because it
    looks like decoupling. A name claimed by two different directories maps to
    None: ambiguous, refused, declared in capabilities().cannotResolve.
    """
    from ..manifest import iter_project_files

    key = str(Path(root).resolve())
    if key in _PKG_CACHE:
        return _PKG_CACHE[key]
    out: dict[str, Path | None] = {}
    for f in iter_project_files(root):
        if f.name != "__init__.py":
            continue
        pkg_dir = f.parent
        try:
            if (pkg_dir.parent / "__init__.py").exists():
                continue                 # nested package — not a top-level root
        except OSError:
            continue
        name = pkg_dir.name
        if name in out:
            if out[name] is not None and out[name] != pkg_dir:
                out[name] = None
        else:
            out[name] = pkg_dir
    _PKG_CACHE[key] = out
    return out

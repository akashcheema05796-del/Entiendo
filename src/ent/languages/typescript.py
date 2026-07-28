"""TypeScript / JavaScript import extraction (spike).

A second `LanguageExtractor`, to prove the seam carries a non-Python language.
It is deliberately dependency-free: rather than pull in a TS parser, it finds
import *specifiers* with a small set of regexes over the source and resolves the
**relative** ones (`./`, `../`) to a project file. That covers the forms that
create unit→unit edges:

    import x from './m'          import { a } from '../lib/m'
    import * as ns from './m'    import './m'            (side-effect)
    export { a } from './m'      export * from './m'
    const x = require('./m')     await import('./m')     (dynamic)

Resolution mirrors Node/TS module resolution enough for real relative imports:
try the specifier with each known extension, then as a directory `index.*`, and
map a written `.js`/`.mjs` specifier onto a `.ts` source (the TS convention).

Spike scope — deliberately out for now, and where a real implementation goes:
  - bare specifiers (`react`, `@scope/pkg`) are treated as external and dropped;
  - `tsconfig` path aliases (`paths` / `baseUrl`) are not resolved;
  - the regex sees import-like text in comments or strings — a tokenizer would
    remove that ambiguity. These are the first things to harden past the spike.
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import ImportEdge

# Source extensions we resolve against, in resolution priority (TS before JS).
_SOURCE_EXTS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
# A written specifier ending in one of these is remapped onto a source ext.
_REMAP = {".js": _SOURCE_EXTS, ".mjs": _SOURCE_EXTS, ".cjs": _SOURCE_EXTS,
          ".jsx": _SOURCE_EXTS}

# `import …/export … from '<spec>'`
_FROM = re.compile(r"""\b(?:import|export)\b[^;'"]*?\bfrom\s*['"]([^'"]+)['"]""")
# bare side-effect `import '<spec>'`
_SIDE_EFFECT = re.compile(r"""\bimport\s*['"]([^'"]+)['"]""")
# `require('<spec>')` and dynamic `import('<spec>')`
_CALL = re.compile(r"""\b(?:require|import)\s*\(\s*['"]([^'"]+)['"]\s*\)""")


class TypeScriptExtractor:
    name = "typescript"
    extensions = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")

    def resolved_imports(self, file: Path, root: Path) -> list[ImportEdge]:
        try:
            src = file.read_text()
        except (UnicodeDecodeError, OSError):
            return []
        specifiers: list[str] = []
        for pat in (_FROM, _SIDE_EFFECT, _CALL):
            specifiers.extend(pat.findall(src))

        out: list[ImportEdge] = []
        seen: set[Path] = set()
        for spec in specifiers:
            if not _is_relative(spec):
                continue                      # bare/external specifier — dropped
            target = _resolve(spec, file, root)
            if target is not None and target not in seen and target != file.resolve():
                seen.add(target)
                out.append(ImportEdge(target=target, detail=spec))
        return out


def _is_relative(spec: str) -> bool:
    return spec.startswith("./") or spec.startswith("../") or spec == "." or spec == ".."


def _resolve(spec: str, importing: Path, root: Path) -> Path | None:
    base = (importing.parent / spec)
    root = root.resolve()

    candidates: list[Path] = []
    # A written extension that maps to a source ext (import './m.js' → m.ts).
    if base.suffix in _REMAP:
        stem = base.with_suffix("")
        candidates += [stem.with_suffix(e) for e in _REMAP[base.suffix]]
        candidates.append(base)                       # or the literal file
    elif base.suffix in _SOURCE_EXTS:
        candidates.append(base)
    else:
        # extensionless: try each source ext, then a directory index.*
        candidates += [base.with_suffix(e) for e in _SOURCE_EXTS]
        candidates += [base / f"index{e}" for e in _SOURCE_EXTS]

    for cand in candidates:
        if cand.exists() and cand.is_file():
            resolved = cand.resolve()
            try:                                        # must stay inside the project
                resolved.relative_to(root)
            except ValueError:
                return None
            return resolved
    return None

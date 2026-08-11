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

Non-relative specifiers resolve through `tsconfig.json` when present: `paths`
aliases (`@app/*` → `src/*`) and `baseUrl`-relative imports (`utils/x` under
`baseUrl: ./src`). Genuinely external packages (`react`, `@scope/pkg`) match no
alias and resolve to no project file, so they're dropped.

Spike scope — deliberately out for now, and where a real implementation goes:
  - the regex sees import-like text in comments or strings — a tokenizer would
    remove that ambiguity;
  - `tsconfig` is read with light JSONC tolerance (strips comments / trailing
    commas) rather than a real JSONC parser, and `extends` chains aren't followed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .base import AdapterCapabilities, ImportEdge

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

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            grade="regex-poc",
            evidenceTag="ts-poc",
            cannotResolve=(
                "import-like text inside comments or strings (regex, no tokenizer)",
                "tsconfig `extends` chains (only the local tsconfig is read)",
                "non-relative specifiers with no tsconfig alias or baseUrl match",
                "type-directed resolution of any kind — no compiler behind this",
            ))

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
            if _is_relative(spec):
                target = _resolve(spec, file, root)
            else:
                target = _resolve_alias(spec, root)     # tsconfig paths / baseUrl
            if target is not None and target not in seen and target != file.resolve():
                seen.add(target)
                out.append(ImportEdge(target=target, detail=spec))
        return out


def _is_relative(spec: str) -> bool:
    return spec.startswith("./") or spec.startswith("../") or spec == "." or spec == ".."


def _resolve_module_path(base: Path, root: Path) -> Path | None:
    """Resolve a module base (no importer context) to a project file, or None.

    Tries the base with each source extension, a directory `index.*`, and the
    `.js`→`.ts` remap — the shared step for relative and alias resolution.
    """
    candidates: list[Path] = []
    if base.suffix in _REMAP:
        stem = base.with_suffix("")
        candidates += [stem.with_suffix(e) for e in _REMAP[base.suffix]]
        candidates.append(base)                       # or the literal file
    elif base.suffix in _SOURCE_EXTS:
        candidates.append(base)
    else:
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


def _resolve(spec: str, importing: Path, root: Path) -> Path | None:
    return _resolve_module_path(importing.parent / spec, root.resolve())


# --------------------------------------------------------------------------- #
# tsconfig path aliases + baseUrl
# --------------------------------------------------------------------------- #

def _strip_jsonc(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)   # block comments
    text = re.sub(r"//[^\n]*", "", text)                # line comments
    text = re.sub(r",(\s*[}\]])", r"\1", text)          # trailing commas
    return text


def _load_tsconfig(root: Path) -> tuple[Path | None, dict[str, list[str]]]:
    """Return (baseDir, paths) from tsconfig.json, or (None, {}) if absent/broken.

    `baseDir` is where `paths` targets and baseUrl-relative imports resolve from:
    `root / baseUrl`, or `root` when no baseUrl (TS 4.1+ allows paths without it).
    """
    path = root / "tsconfig.json"
    if not path.exists():
        return None, {}
    try:
        data = json.loads(_strip_jsonc(path.read_text()))
    except (ValueError, OSError):
        return None, {}
    opts = (data or {}).get("compilerOptions", {}) or {}
    base_url = opts.get("baseUrl")
    base_dir = (root / base_url).resolve() if base_url else root.resolve()
    paths = opts.get("paths", {}) or {}
    return base_dir, paths


def _match_alias(pattern: str, spec: str) -> str | None:
    """The `*`-captured segment if `spec` matches the alias `pattern`, else None."""
    if "*" in pattern:
        prefix, _, suffix = pattern.partition("*")
        if spec.startswith(prefix) and spec.endswith(suffix) \
                and len(spec) >= len(prefix) + len(suffix):
            return spec[len(prefix): len(spec) - len(suffix)] if suffix else spec[len(prefix):]
        return None
    return "" if spec == pattern else None


# --------------------------------------------------------------------------- #
# workspace packages (v7) — pnpm/npm monorepos import siblings BY NAME
# --------------------------------------------------------------------------- #

_WS_CACHE: dict[str, dict[str, Path]] = {}


def _workspace_map(root: Path) -> dict[str, Path]:
    """package name → package dir for every workspace member, cached per root.

    Reads pnpm-workspace.yaml `packages:` globs and package.json `workspaces`;
    without this, every `import "@scope/pkg"` between siblings is INVISIBLE to
    the map — the worst kind of missing edge, because it looks like decoupling.
    """
    key = str(root.resolve())
    if key in _WS_CACHE:
        return _WS_CACHE[key]
    globs: list[str] = []
    pw = root / "pnpm-workspace.yaml"
    if pw.exists():
        in_packages = False
        for line in pw.read_text(errors="replace").splitlines():
            if not line.startswith((" ", "\t", "-")):    # a new top-level key
                in_packages = line.strip().startswith("packages:")
                continue
            line = line.strip()
            if in_packages and line.startswith("- "):
                globs.append(line[2:].strip().strip("'\""))
    pj = root / "package.json"
    if pj.exists():
        try:
            ws = json.loads(pj.read_text()).get("workspaces")
            globs += ws if isinstance(ws, list) else (ws or {}).get("packages", [])
        except (json.JSONDecodeError, OSError):
            pass
    out: dict[str, Path] = {}
    for g in globs:
        g = g.rstrip("/")
        if not g or g.startswith("!"):                   # exclusions/blank: skip
            continue
        try:
            dirs = [root] if g == "." else list(root.glob(g))
        except (OSError, ValueError, IndexError, NotImplementedError):
            continue                                     # hostile pattern — skip
        for d in dirs:
            mp = d / "package.json"
            if not mp.is_file():
                continue
            try:
                name = json.loads(mp.read_text()).get("name")
            except (json.JSONDecodeError, OSError):
                continue
            if name:
                out[name] = d
    _WS_CACHE[key] = out
    return out


def _resolve_workspace(spec: str, root: Path) -> Path | None:
    """Resolve `@scope/pkg` or `@scope/pkg/subpath` to a sibling workspace file."""
    ws = _workspace_map(root)
    if not ws:
        return None
    parts = spec.split("/")
    for cut in (2, 1):                       # scoped names use two segments
        name, sub = "/".join(parts[:cut]), "/".join(parts[cut:])
        d = ws.get(name)
        if d is None:
            continue
        root_r = root.resolve()
        for base in ((d / sub) if sub else None, d / "src" / sub if sub else None,
                     d / "src" / "index", d / "index"):
            if base is None:
                continue
            resolved = _resolve_module_path(base, root_r)
            if resolved is not None:
                return resolved
    return None


def _resolve_alias(spec: str, root: Path) -> Path | None:
    ws = _resolve_workspace(spec, root)
    if ws is not None:
        return ws
    base_dir, paths = _load_tsconfig(root)
    if base_dir is None:
        return None                                     # no tsconfig → external, drop
    root = root.resolve()
    for pattern, targets in paths.items():
        captured = _match_alias(pattern, spec)
        if captured is None:
            continue
        for tgt in targets or []:
            sub = tgt.replace("*", captured) if "*" in tgt else tgt
            resolved = _resolve_module_path(base_dir / sub, root)
            if resolved is not None:
                return resolved
    # baseUrl-relative bare import (e.g. `utils/x` under baseUrl: ./src)
    return _resolve_module_path(base_dir / spec, root)

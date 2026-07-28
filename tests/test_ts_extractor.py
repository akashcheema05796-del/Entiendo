"""TypeScript/JS extractor spike (gap analysis §1).

Proves the language-agnostic extractor seam carries a second language: the TS
extractor resolves the real import forms to intra-project files, and — the point
of the spike — `extract()` reconciles a TypeScript project (declared → verified,
undeclared → drift) with **no change to the reconciler or the Python path**.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")

from ent import languages  # noqa: E402
from ent.extractor import extract  # noqa: E402
from ent.languages.typescript import TypeScriptExtractor  # noqa: E402


def _mkproject(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tmp_path


def _node(node_id: str, *, claims: list[str], calls: list[str] | None = None) -> str:
    calls_yaml = "\n".join(f"    - {c}" for c in (calls or []))
    claims_yaml = "\n".join(f"  - {c}" for c in claims)
    return f"""\
apiVersion: entiendo/v1
kind: Node
id: {node_id}
name: {node_id}
nodeKind: compute
owner: me
claims:
{claims_yaml}
contract:
  sideEffects: none
dependencies:
  calls:
{calls_yaml}
"""


# --------------------------------------------------------------------------- #
# the registry seam
# --------------------------------------------------------------------------- #

def test_registry_picks_extractor_by_extension() -> None:
    assert languages.for_file(Path("a/b.ts")).name == "typescript"
    assert languages.for_file(Path("a/b.tsx")).name == "typescript"
    assert languages.for_file(Path("a/b.py")).name == "python"
    assert languages.for_file(Path("a/b.md")) is None
    assert {".ts", ".tsx", ".py"} <= languages.extensions()


# --------------------------------------------------------------------------- #
# resolution of the real import forms
# --------------------------------------------------------------------------- #

def test_resolves_relative_import_forms(tmp_path: Path) -> None:
    root = _mkproject(tmp_path, {
        "src/a.ts": """\
import def1 from './b';
import { x } from './sub/c';
export { y } from '../src/d';
import './e';                       // side-effect
const f = require('./f');
const g = await import('./g');
import ext from 'react';           // external — dropped
""",
        "src/b.ts": "export default 1;\n",
        "src/sub/c.ts": "export const x = 1;\n",
        "src/d.ts": "export const y = 1;\n",
        "src/e.ts": "console.log('side effect');\n",
        "src/f.ts": "module.exports = 1;\n",
        "src/g.ts": "export const g = 1;\n",
    })
    edges = TypeScriptExtractor().resolved_imports(root / "src/a.ts", root)
    targets = {e.target.relative_to(root.resolve()).as_posix() for e in edges}
    assert targets == {
        "src/b.ts", "src/sub/c.ts", "src/d.ts",
        "src/e.ts", "src/f.ts", "src/g.ts",
    }
    # 'react' (a bare specifier) never resolves to a project file
    assert not any("react" in e.detail and e.target.exists() is False for e in edges)


def test_resolves_directory_index_and_js_to_ts(tmp_path: Path) -> None:
    root = _mkproject(tmp_path, {
        "src/a.ts": "import { m } from './mod';\nimport './pkg';\n",
        "src/mod.ts": "export const m = 1;\n",           # './mod' → mod.ts
        "src/pkg/index.ts": "export {};\n",              # './pkg' → pkg/index.ts
    })
    edges = TypeScriptExtractor().resolved_imports(root / "src/a.ts", root)
    targets = {e.target.relative_to(root.resolve()).as_posix() for e in edges}
    assert targets == {"src/mod.ts", "src/pkg/index.ts"}


def test_js_specifier_maps_onto_ts_source(tmp_path: Path) -> None:
    # TS convention: the specifier is written '.js' but the source file is '.ts'.
    root = _mkproject(tmp_path, {
        "src/a.ts": "import { m } from './mod.js';\n",
        "src/mod.ts": "export const m = 1;\n",
    })
    edges = TypeScriptExtractor().resolved_imports(root / "src/a.ts", root)
    assert {e.target.relative_to(root.resolve()).as_posix() for e in edges} == {"src/mod.ts"}


def test_bare_and_unresolvable_specifiers_dropped(tmp_path: Path) -> None:
    root = _mkproject(tmp_path, {
        "src/a.ts": "import x from 'react';\nimport y from '@scope/pkg';\n"
                    "import z from './missing';\n",
    })
    assert TypeScriptExtractor().resolved_imports(root / "src/a.ts", root) == []


# --------------------------------------------------------------------------- #
# end to end: the reconciler carries TypeScript unchanged
# --------------------------------------------------------------------------- #

def test_ts_declared_dependency_is_verified_not_drift(tmp_path: Path) -> None:
    root = _mkproject(tmp_path, {
        "a/index.ts": "import { thing } from '../b/thing';\nexport const a = thing;\n",
        "b/thing.ts": "export const thing = 1;\n",
        "a/entiendo.node.yaml": _node("a.one", claims=["a/index.ts"], calls=["b.two"]),
        "b/entiendo.node.yaml": _node("b.two", claims=["b/thing.ts"]),
    })
    result = extract(root)
    assert result.ok, result.errors
    edge = next(e for e in result.graph["edges"] if e["from"] == "a.one" and e["to"] == "b.two")
    assert edge["declared"] and edge["verified"]


def test_ts_undeclared_import_is_drift(tmp_path: Path) -> None:
    root = _mkproject(tmp_path, {
        "a/index.ts": "import { thing } from '../b/thing';\nexport const a = thing;\n",
        "b/thing.ts": "export const thing = 1;\n",
        "a/entiendo.node.yaml": _node("a.one", claims=["a/index.ts"]),  # no deps
        "b/entiendo.node.yaml": _node("b.two", claims=["b/thing.ts"]),
    })
    result = extract(root)
    assert not result.ok
    assert any("a.one -> b.two" in e for e in result.errors)

"""TypeScript tsconfig path-alias resolution (gap analysis §1 follow-up).

The spike dropped every non-relative specifier; real TS projects import
intra-project modules through `tsconfig` `paths` aliases (`@app/*`) and
`baseUrl`. These resolve those to project files — while genuine external
packages (matching no alias) stay dropped, and a project with no tsconfig is
unchanged from the spike.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")

from ent.extractor import extract  # noqa: E402
from ent.languages.typescript import TypeScriptExtractor  # noqa: E402


def _mkproject(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tmp_path


def _targets(root: Path, rel: str) -> set[str]:
    edges = TypeScriptExtractor().resolved_imports(root / rel, root)
    return {e.target.relative_to(root.resolve()).as_posix() for e in edges}


TSCONFIG = """\
{
  // path aliases for the app
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@app/*": ["src/*"],
      "@lib": ["src/lib/index.ts"],
    },
  },
}
"""


def test_paths_star_alias_resolves(tmp_path: Path) -> None:
    root = _mkproject(tmp_path, {
        "tsconfig.json": TSCONFIG,
        "src/a.ts": "import { u } from '@app/util';\n",
        "src/util.ts": "export const u = 1;\n",
    })
    assert _targets(root, "src/a.ts") == {"src/util.ts"}


def test_exact_alias_resolves_to_named_file(tmp_path: Path) -> None:
    root = _mkproject(tmp_path, {
        "tsconfig.json": TSCONFIG,
        "src/a.ts": "import { l } from '@lib';\n",
        "src/lib/index.ts": "export const l = 1;\n",
    })
    assert _targets(root, "src/a.ts") == {"src/lib/index.ts"}


def test_baseurl_relative_bare_import_resolves(tmp_path: Path) -> None:
    root = _mkproject(tmp_path, {
        "tsconfig.json": '{"compilerOptions": {"baseUrl": "./src"}}',
        "src/a.ts": "import { t } from 'thing';\n",     # baseUrl-relative, no alias
        "src/thing.ts": "export const t = 1;\n",
    })
    assert _targets(root, "src/a.ts") == {"src/thing.ts"}


def test_external_package_still_dropped_with_tsconfig(tmp_path: Path) -> None:
    root = _mkproject(tmp_path, {
        "tsconfig.json": TSCONFIG,
        "src/a.ts": "import React from 'react';\nimport z from '@scope/pkg';\n",
    })
    assert _targets(root, "src/a.ts") == set()


def test_no_tsconfig_drops_bare_specifiers(tmp_path: Path) -> None:
    # unchanged from the spike: without tsconfig, non-relative specifiers drop
    root = _mkproject(tmp_path, {
        "src/a.ts": "import { u } from '@app/util';\n",
        "src/util.ts": "export const u = 1;\n",
    })
    assert _targets(root, "src/a.ts") == set()


def test_broken_tsconfig_is_ignored_not_fatal(tmp_path: Path) -> None:
    root = _mkproject(tmp_path, {
        "tsconfig.json": "{ this is not json",
        "src/a.ts": "import { u } from '@app/util';\nimport { r } from './rel';\n",
        "src/util.ts": "export const u = 1;\n",
        "src/rel.ts": "export const r = 1;\n",
    })
    # alias unresolved (broken config), but relative imports still work
    assert _targets(root, "src/a.ts") == {"src/rel.ts"}


def test_end_to_end_extract_over_aliased_ts_project(tmp_path: Path) -> None:
    manifest = """\
apiVersion: entiendo/v1
kind: Node
id: {id}
name: {id}
nodeKind: compute
owner: me
claims:
  - {claim}
contract:
  sideEffects: none
dependencies:
  calls: {calls}
"""
    root = _mkproject(tmp_path, {
        "tsconfig.json": TSCONFIG,
        "src/a/index.ts": "import { u } from '@app/b/thing';\nexport const a = u;\n",
        "src/b/thing.ts": "export const u = 1;\n",
        "src/a/entiendo.node.yaml": manifest.format(id="a.one", claim="src/a/index.ts", calls="[b.two]"),
        "src/b/entiendo.node.yaml": manifest.format(id="b.two", claim="src/b/thing.ts", calls="[]"),
    })
    result = extract(root)
    assert result.ok, result.errors
    edge = next(e for e in result.graph["edges"] if e["from"] == "a.one" and e["to"] == "b.two")
    assert edge["declared"] and edge["verified"]        # alias import verified the edge

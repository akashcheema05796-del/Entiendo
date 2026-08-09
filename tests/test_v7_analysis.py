"""v7 — analysis-engine truthfulness (gaps found retrofitting a real monorepo).

1. Glob claims: a unit can own `src/pkg/**/*.py` instead of enumerating
   thousands of paths; expansion flows through ownership, coverage, hashing,
   and the write authority.
2. Workspace package imports: pnpm/npm monorepo siblings import each other BY
   NAME — those edges were invisible before, which looked like decoupling.
3. Dependency cycles: strongly-connected unit groups are named in graph.json,
   the CLI, and the dossier — a warning, never a gate.
4. TS/JS blind spots: dynamic import()/require()/child_process/network clients
   flagged the same way Python's were.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import claims as claims_mod  # noqa: E402
from ent.extractor import extract  # noqa: E402
from ent.manifest import Node, load  # noqa: E402
from ent.version import compute_version  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def _mk(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tmp_path


def _node_yaml(node_id: str, claims: list[str], calls: list[str] | None = None) -> str:
    claims_yaml = "\n".join(f"  - '{c}'" for c in claims)
    dep = ""
    if calls:
        dep = "dependencies:\n  calls:\n" + "\n".join(f"    - {c}" for c in calls) + "\n"
    return (f"apiVersion: entiendo/v1\nkind: Node\nid: {node_id}\nname: {node_id}\n"
            f"nodeKind: compute\nowner: me\nclaims:\n{claims_yaml}\n"
            f"contract:\n  sideEffects: none\n{dep}")


# --------------------------------------------------------------------------- #
# 1. glob claims
# --------------------------------------------------------------------------- #

def test_glob_claims_expand_deterministically(tmp_path: Path) -> None:
    _mk(tmp_path, {"src/a/one.py": "x=1\n", "src/a/sub/two.py": "y=2\n",
                   "src/a/readme.md": "hi\n", "src/b/other.py": "z=3\n"})
    out = claims_mod.expand_claims(tmp_path, ["src/a/**/*.py", "src/b/other.py"])
    assert out == ["src/a/one.py", "src/a/sub/two.py", "src/b/other.py"]
    # literal claims pass through even when missing (downstream decides)
    assert claims_mod.expand_claims(tmp_path, ["src/ghost.py"]) == ["src/ghost.py"]


def test_glob_claims_drive_ownership_coverage_and_edges(tmp_path: Path) -> None:
    root = _mk(tmp_path, {
        "pkg/core/a.py": "from helpers.util import x\n",
        "pkg/core/b.py": "y = 1\n",
        "helpers/util.py": "x = 1\n",
        "pkg/entiendo.node.yaml": _node_yaml("app.core", ["pkg/core/**/*.py"],
                                             calls=["app.helpers"]),
        "helpers/entiendo.node.yaml": _node_yaml("app.helpers", ["helpers/*.py"]),
    })
    result = extract(root)
    assert result.ok, result.errors
    core = next(n for n in result.graph["nodes"] if n["id"] == "app.core")
    assert core["claimedFileCount"] == 2                 # true mass, not pattern count
    assert core["claims"] == ["pkg/core/**/*.py"]        # the pattern stays visible
    edge = next(e for e in result.graph["edges"]
                if e["from"] == "app.core" and e["to"] == "app.helpers")
    assert edge["verified"]                              # found via expanded claims
    assert result.coverage["claimedCount"] == 3


def test_glob_claims_authorise_writes_and_move_the_version(tmp_path: Path) -> None:
    root = _mk(tmp_path, {
        "src/a/one.py": "x=1\n",
        "src/entiendo.node.yaml": _node_yaml("app.a", ["src/a/**/*.py"]),
    })
    node = Node.from_manifest(load(root / "src/entiendo.node.yaml"),
                              root / "src/entiendo.node.yaml")
    assert claims_mod.is_within_claims(root, node, "src/a/one.py")
    assert not claims_mod.is_within_claims(root, node, "src/entiendo.node.yaml")
    v1 = compute_version(node, root)["composite"]
    (root / "src/a/one.py").write_text("x=2\n")
    assert compute_version(node, root)["composite"] != v1  # glob content is hashed


def test_double_claim_via_overlapping_globs_is_structural(tmp_path: Path) -> None:
    root = _mk(tmp_path, {
        "src/a/one.py": "x=1\n",
        "src/entiendo.node.yaml": _node_yaml("app.a", ["src/a/**/*.py"]),
        "entiendo.node.yaml": _node_yaml("app.all", ["src/**/*.py"]),
    })
    result = extract(root)
    assert not result.ok
    assert any("claimed by multiple nodes" in e for e in result.errors)


# --------------------------------------------------------------------------- #
# 2. workspace package-name imports
# --------------------------------------------------------------------------- #

def test_pnpm_workspace_imports_resolve_to_sibling_packages(tmp_path: Path) -> None:
    root = _mk(tmp_path, {
        "pnpm-workspace.yaml": "packages:\n  - 'packages/*'\n",
        "packages/core/package.json": '{"name": "@app/core"}',
        "packages/core/src/index.ts": "export const c = 1;\n",
        "packages/ui/package.json": '{"name": "@app/ui"}',
        "packages/ui/src/app.ts": 'import { c } from "@app/core";\nexport const u = c;\n',
        "packages/ui/entiendo.node.yaml": _node_yaml("app.ui", ["packages/ui/src/app.ts"],
                                                     calls=["app.core"]),
        "packages/core/entiendo.node.yaml": _node_yaml("app.core",
                                                       ["packages/core/src/index.ts"]),
    })
    result = extract(root)
    assert result.ok, result.errors
    edge = next(e for e in result.graph["edges"]
                if e["from"] == "app.ui" and e["to"] == "app.core")
    assert edge["verified"] and edge["verificationSource"] == ["ts-poc"]


def test_npm_workspaces_field_and_subpath_imports(tmp_path: Path) -> None:
    root = _mk(tmp_path, {
        "package.json": '{"workspaces": ["libs/*"]}',
        "libs/util/package.json": '{"name": "util"}',
        "libs/util/helpers.ts": "export const h = 1;\n",
        "libs/app/package.json": '{"name": "app"}',
        "libs/app/main.ts": 'import { h } from "util/helpers";\n',
        "libs/app/entiendo.node.yaml": _node_yaml("m.app", ["libs/app/main.ts"],
                                                  calls=["m.util"]),
        "libs/util/entiendo.node.yaml": _node_yaml("m.util", ["libs/util/helpers.ts"]),
    })
    result = extract(root)
    assert result.ok, result.errors
    assert any(e["from"] == "m.app" and e["to"] == "m.util" and e["verified"]
               for e in result.graph["edges"])


# --------------------------------------------------------------------------- #
# 3. dependency cycles
# --------------------------------------------------------------------------- #

def test_cycles_are_named_not_silent(tmp_path: Path) -> None:
    root = _mk(tmp_path, {
        "a/x.py": "from b.y import q\n", "b/y.py": "from a.x import r\nq=1\n",
        "c/z.py": "w=1\n",
        "a/entiendo.node.yaml": _node_yaml("m.a", ["a/x.py"], calls=["m.b"]),
        "b/entiendo.node.yaml": _node_yaml("m.b", ["b/y.py"], calls=["m.a"]),
        "c/entiendo.node.yaml": _node_yaml("m.c", ["c/z.py"]),
    })
    result = extract(root)
    assert result.ok, result.errors                     # a cycle is NOT a failure
    assert result.graph["dependencyCycles"] == [["m.a", "m.b"]]


def test_acyclic_graph_reports_no_cycles(tmp_path: Path) -> None:
    root = _mk(tmp_path, {
        "a/x.py": "from b.y import q\n", "b/y.py": "q=1\n",
        "a/entiendo.node.yaml": _node_yaml("m.a", ["a/x.py"], calls=["m.b"]),
        "b/entiendo.node.yaml": _node_yaml("m.b", ["b/y.py"]),
    })
    assert extract(root).graph["dependencyCycles"] == []


def test_unit_window_carries_cycle_membership() -> None:
    html = (REPO_ROOT / "src/ent/universe.html").read_text()
    assert "dependencyCycles" in html and "circular dependency with" in html


# --------------------------------------------------------------------------- #
# 4. TS/JS blind spots
# --------------------------------------------------------------------------- #

def test_ts_dynamic_constructs_are_flagged(tmp_path: Path) -> None:
    root = _mk(tmp_path, {
        "src/dyn.ts": ('const m = await import("./plugin.js");\n'
                       'const cp = require("child_process");\n'
                       'await fetch("https://api.example.com");\n'),
        "src/entiendo.node.yaml": _node_yaml("m.dyn", ["src/dyn.ts"]),
    })
    warns = extract(root).graph["possibleUndeclaredDynamicDep"]
    patterns = {w["pattern"] for w in warns if w["node"] == "m.dyn"}
    assert {"dynamic-import", "require", "child_process", "network-client"} <= patterns

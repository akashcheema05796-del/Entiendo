"""Discovery stops at nested project roots.

A subdirectory with its own `entiendo/` control-plane dir or its own `.git`
is a separate project: its manifests' claims resolve against THAT root, so
sweeping them into a parent's discovery misroots every claim. Found live:
`ent validate` (and therefore `ent mcp`) at the Entiendo repo root swallowed
examples/refundly + examples/greenfield and refused to start.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent.manifest import discover  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def _manifest(dirpath: Path, node_id: str) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / "entiendo.node.yaml"
    path.write_text(f"apiVersion: entiendo/v1\nid: {node_id}\n")
    return path


def test_discovery_prunes_nested_entiendo_projects(tmp_path: Path) -> None:
    mine = _manifest(tmp_path / "src/thing", "outer.thing")
    nested = tmp_path / "examples/demo"
    (nested / "entiendo").mkdir(parents=True)          # its own control plane
    _manifest(nested / "src/unit", "demo.unit")
    assert discover(tmp_path) == [mine]


def test_discovery_prunes_nested_git_repos(tmp_path: Path) -> None:
    mine = _manifest(tmp_path / "src/thing", "outer.thing")
    vendored = tmp_path / "vendor/clone"
    (vendored / ".git").mkdir(parents=True)            # a vendored checkout
    _manifest(vendored / "src/unit", "vendored.unit")
    assert discover(tmp_path) == [mine]


def test_own_root_markers_do_not_prune_the_root(tmp_path: Path) -> None:
    """The discovery root itself normally HAS entiendo/ and .git — only
    markers strictly below the root mean "someone else's project"."""
    (tmp_path / "entiendo").mkdir()
    (tmp_path / ".git").mkdir()
    mine = _manifest(tmp_path / "src/thing", "outer.thing")
    assert discover(tmp_path) == [mine]


def test_examples_are_invisible_from_the_entiendo_repo_root() -> None:
    """The live regression: the examples are self-contained projects that must
    not leak into a root-level discovery. (The repo now owns units of its own —
    the self-host retrofit — so the assertion is about WHERE manifests come
    from, not that there are none.)"""
    found = discover(REPO_ROOT)
    assert found, "the self-host units should be discovered"
    for path in found:
        rel = path.relative_to(REPO_ROOT)
        assert rel.parts[0] == "units", f"manifest outside units/: {rel}"
        assert "examples" not in rel.parts, f"example project leaked: {rel}"


# --------------------------------------------------------------------------- #
# the `ent mcp` startup gate
# --------------------------------------------------------------------------- #

def _run_mcp(root: Path) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        [sys.executable, "-m", "ent.cli", "mcp", "--root", str(root)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)


def test_mcp_starts_on_an_unmanaged_repo(tmp_path: Path) -> None:
    """Zero manifests is the retrofit starting state, not an invalid one —
    the server must come up (and exit 0 on stdin EOF) without --allow-invalid."""
    pytest.importorskip("mcp")
    proc = _run_mcp(tmp_path)
    assert proc.returncode == 0
    assert "manifests are invalid" not in proc.stdout


def test_selfhost_repo_validates_and_reconciles() -> None:
    """The Entiendo repo manages itself: 14 units, every file claimed or
    explicitly acknowledged, declared edges verified against real imports."""
    from ent.extractor import extract
    from ent.validation import validate_root

    assert validate_root(REPO_ROOT).ok
    result = extract(REPO_ROOT)
    assert result.ok, result.errors
    assert len(result.graph["nodes"]) == 14
    assert result.coverage["unaccountedCount"] == 0, result.coverage["unaccounted"]


def test_selfhost_runnable_units_are_green() -> None:
    """The units with a single-arg entrypoint actually execute their smoke.

    Via the sandbox subprocess — the production path. In-process run_tier0 on
    ent's OWN units would purge live ent.* modules from sys.modules (the
    entrypoint freshness cache), splitting module state under this very test
    run. Cross-process isolation is the correct execution boundary here."""
    from ent import sandbox
    from ent.manifest import find_node

    for uid in ("ent.contracts", "ent.retrofit"):
        res = sandbox.run_sandboxed(REPO_ROOT, find_node(REPO_ROOT, uid))
        assert res["verdict"] == "GREEN", (uid, res)


def test_mcp_still_refuses_actually_invalid_manifests(tmp_path: Path) -> None:
    (tmp_path / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nid: broken.unit\nclaims: [missing.py]\n")
    proc = _run_mcp(tmp_path)
    assert proc.returncode == 2
    assert "manifests are invalid" in proc.stdout

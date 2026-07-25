"""MCP server tool tests (L5, inverted). Pure tool functions — no transport.

`ent mcp` exposes the same scoped-edit surface as `ent serve`, but Claude Code
is the model. The transport (FastMCP/stdio) is glue; the guarantees live in the
pure `tool_*` functions, which is what these tests exercise directly — exactly
as `test_server.py` tests `handle_api` without a socket.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import mcp_server  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"


def _tmp_node(tmp_path: Path) -> Path:
    """A self-contained node (no intra-project imports → deterministic tier0)."""
    (tmp_path / "mod.py").write_text(
        "import ent\n\n@ent.node('demo.thing')\ndef run(req):\n    return {'ok': True}\n"
    )
    (tmp_path / "evals" / "demo.thing").mkdir(parents=True)
    (tmp_path / "evals" / "demo.thing" / "smoke.jsonl").write_text('{"name": "s", "input": {"x": 1}}\n')
    manifest = (
        "apiVersion: entiendo/v1\nkind: Node\nid: demo.thing\nname: Demo\nnodeKind: compute\n"
        "owner: me\nclaims: [mod.py]\n"
        "contract:\n  entrypoint: mod.py::run\n  invariants: [\"output.ok == True\"]\n  sideEffects: none\n"
        "evals:\n  tier0:\n    - type: invariant_check\n    - {type: smoke, fixture: evals/demo.thing/smoke.jsonl}\n"
    )
    mod_dir = tmp_path / "src"
    mod_dir.mkdir()
    (mod_dir / "entiendo.node.yaml").write_text(manifest)
    return tmp_path


# --------------------------------------------------------------------------- #
# (a) apply_edit rejects out-of-claims paths and writes nothing
# --------------------------------------------------------------------------- #

def test_apply_edit_rejects_out_of_claims_and_writes_nothing(tmp_path: Path) -> None:
    root = _tmp_node(tmp_path)
    result = mcp_server.tool_apply_edit(
        root, "demo.thing", "touch a file outside claims",
        [{"path": "secret.py", "content": "print('nope')\n"}],
    )
    # every path was outside claims → the whole edit is refused, nothing written
    assert "error" in result
    assert "secret.py" in result["rejected"]
    assert not (root / "secret.py").exists()
    # the claimed file is untouched
    assert (root / "mod.py").read_text() == (
        "import ent\n\n@ent.node('demo.thing')\ndef run(req):\n    return {'ok': True}\n"
    )


# --------------------------------------------------------------------------- #
# (b) apply_edit within claims writes, reruns tier0, GREEN + ready-to-merge
# --------------------------------------------------------------------------- #

def test_apply_edit_within_claims_writes_and_is_green(tmp_path: Path) -> None:
    root = _tmp_node(tmp_path)
    new_body = "import ent\n\n@ent.node('demo.thing')\ndef run(req):\n    return {'ok': True, 'edited': 1}\n"
    result = mcp_server.tool_apply_edit(
        root, "demo.thing", "add a harmless field",
        [{"path": "mod.py", "content": new_body}],
    )
    assert result["changed"] == ["mod.py"]
    assert result["rejected"] == []
    assert result["outcome"]["verdict"] == "GREEN"
    assert result["outcome"]["status"] == "ready-to-merge"
    assert (root / "mod.py").read_text() == new_body  # actually written


# --------------------------------------------------------------------------- #
# (c) revert_node restores backups
# --------------------------------------------------------------------------- #

def test_revert_node_restores_backup(tmp_path: Path) -> None:
    root = _tmp_node(tmp_path)
    original = (root / "mod.py").read_text()
    mcp_server.tool_apply_edit(
        root, "demo.thing", "change it",
        [{"path": "mod.py", "content": "import ent\n\n@ent.node('demo.thing')\ndef run(req):\n    return {'ok': True, 'x': 1}\n"}],
    )
    assert (root / "mod.py").read_text() != original

    result = mcp_server.tool_revert_node(root, "demo.thing")
    assert result["restored"] == ["mod.py"]
    assert result["verdict"] == "GREEN"
    assert (root / "mod.py").read_text() == original


# --------------------------------------------------------------------------- #
# (d) get_node_context returns claimed files + neighbour contracts only
# --------------------------------------------------------------------------- #

def test_get_node_context_scopes_to_claims_and_neighbour_contracts() -> None:
    ctx = mcp_server.tool_get_node_context(GREENFIELD, "retrieval.chunk_ranker")

    # own claimed file body is loaded...
    assert "src/retrieval/ranker.py" in ctx["claimedFiles"]
    # ...but no neighbour's file body leaks in
    assert "src/vector_store/store.py" not in ctx["claimedFiles"]

    # neighbours appear as CONTRACTS ONLY (no bodies), keyed by node id
    assert "retrieval.vector_store" in ctx["neighbourContracts"]
    neighbour = ctx["neighbourContracts"]["retrieval.vector_store"]
    assert isinstance(neighbour, dict)
    # a contract, not a file body
    assert "sideEffects" in neighbour or "invariants" in neighbour or "entrypoint" in neighbour


def test_get_node_context_unknown_node_errors() -> None:
    assert "error" in mcp_server.tool_get_node_context(GREENFIELD, "nope.node")

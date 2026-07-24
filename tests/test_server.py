"""L5 server / edit-surface tests (Phase 9). Pure handlers, stub model client."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import server  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"


def stub_client(files: dict[str, str], *, raise_exc: Exception | None = None):
    class _Messages:
        def create(self, **kwargs):
            if raise_exc is not None:
                raise raise_exc
            text = json.dumps({"summary": "ok", "files": [{"path": p, "content": c} for p, c in files.items()]})
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])

    return SimpleNamespace(messages=_Messages())


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
# read-only endpoints (greenfield)
# --------------------------------------------------------------------------- #

def test_graph_endpoint() -> None:
    status, payload = server.handle_api(GREENFIELD, "GET", "/api/graph", None)
    assert status == 200
    assert len(payload["nodes"]) == 5


def test_context_endpoint_scopes_to_node() -> None:
    status, payload = server.handle_api(
        GREENFIELD, "GET", "/api/node/retrieval.chunk_ranker/context", None)
    assert status == 200
    assert "src/retrieval/ranker.py" in payload["claimedFiles"]
    assert "src/vector_store/store.py" not in payload["claimedFiles"]


def test_eval_endpoint() -> None:
    status, payload = server.handle_api(
        GREENFIELD, "POST", "/api/node/retrieval.vector_store/eval", {"tier": "0"})
    assert status == 200
    assert payload["verdict"] == "GREEN"


def test_unknown_node_is_404() -> None:
    status, _ = server.handle_api(GREENFIELD, "GET", "/api/node/nope.node/context", None)
    assert status == 404


# --------------------------------------------------------------------------- #
# edit endpoint (tmp node, stub model)
# --------------------------------------------------------------------------- #

def test_edit_applies_within_claims_and_reruns_tier0(tmp_path: Path) -> None:
    root = _tmp_node(tmp_path)
    client = stub_client({"mod.py": "import ent\n\n@ent.node('demo.thing')\ndef run(req):\n    return {'ok': True, 'edited': 1}\n"})
    status, payload = server.handle_api(
        root, "POST", "/api/node/demo.thing/edit", {"instruction": "add a field"}, client=client)
    assert status == 200
    assert payload["changed"] == ["mod.py"]
    assert payload["outcome"]["verdict"] == "GREEN"
    assert payload["outcome"]["status"] == "ready-to-merge"
    assert "edited" in (root / "mod.py").read_text()  # actually written


def test_edit_rejects_files_outside_claims(tmp_path: Path) -> None:
    root = _tmp_node(tmp_path)
    client = stub_client({
        "mod.py": "import ent\n\n@ent.node('demo.thing')\ndef run(req):\n    return {'ok': True}\n",
        "secret.py": "print('nope')\n",  # not claimed
    })
    status, payload = server.handle_api(
        root, "POST", "/api/node/demo.thing/edit", {"instruction": "x"}, client=client)
    assert status == 200
    assert "secret.py" in payload["rejected"]
    assert not (root / "secret.py").exists()  # never written


def test_edit_red_when_invariant_breaks(tmp_path: Path) -> None:
    root = _tmp_node(tmp_path)
    client = stub_client({"mod.py": "import ent\n\n@ent.node('demo.thing')\ndef run(req):\n    return {'ok': False}\n"})
    status, payload = server.handle_api(
        root, "POST", "/api/node/demo.thing/edit", {"instruction": "break it"}, client=client)
    assert payload["outcome"]["verdict"] == "RED"
    assert payload["outcome"]["status"].startswith("blocked")


def test_revert_restores_backup(tmp_path: Path) -> None:
    root = _tmp_node(tmp_path)
    original = (root / "mod.py").read_text()
    client = stub_client({"mod.py": "import ent\n\n@ent.node('demo.thing')\ndef run(req):\n    return {'ok': True, 'x': 1}\n"})
    server.handle_api(root, "POST", "/api/node/demo.thing/edit", {"instruction": "x"}, client=client)
    assert (root / "mod.py").read_text() != original

    status, payload = server.handle_api(root, "POST", "/api/node/demo.thing/revert", {})
    assert status == 200
    assert (root / "mod.py").read_text() == original


def test_edit_503_when_model_unavailable(tmp_path: Path) -> None:
    root = _tmp_node(tmp_path)
    client = stub_client({}, raise_exc=RuntimeError("no creds"))
    status, payload = server.handle_api(
        root, "POST", "/api/node/demo.thing/edit", {"instruction": "x"}, client=client)
    assert status == 503
    assert "unavailable" in payload["error"]


def test_empty_instruction_is_400(tmp_path: Path) -> None:
    root = _tmp_node(tmp_path)
    status, _ = server.handle_api(root, "POST", "/api/node/demo.thing/edit", {"instruction": "  "},
                                  client=stub_client({}))
    assert status == 400


def test_app_html_is_self_contained() -> None:
    html = server.build_app_html()
    assert html.startswith("<!doctype html>")
    assert "/api/graph" in html

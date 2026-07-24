"""The execution contract (Phase 7 §1) — entrypoint resolution, drift, proposal."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")

from ent.evals.entrypoint import EntrypointDrift, resolve_entrypoint  # noqa: E402
from ent.extractor import extract  # noqa: E402
from ent.manifest import Node  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"


def _node(tmp_path: Path, entrypoint: str, py: str) -> Node:
    import yaml

    (tmp_path / "mod.py").write_text(py)
    raw = {
        "id": "a.b", "name": "A", "nodeKind": "compute", "owner": "me",
        "claims": ["mod.py"],
        "contract": {"entrypoint": entrypoint, "sideEffects": "none"},
    }
    path = tmp_path / "entiendo.node.yaml"
    path.write_text(yaml.safe_dump(raw))  # persist so extract() can discover it
    return Node.from_manifest(raw, path)


def test_resolve_calls_the_entrypoint(tmp_path: Path) -> None:
    node = _node(tmp_path, "mod.py::run", "def run(inp):\n    return {'ok': inp}\n")
    fn = resolve_entrypoint(node, tmp_path)
    assert fn({"x": 1}) == {"ok": {"x": 1}}


def test_decorator_mismatch_is_drift(tmp_path: Path) -> None:
    py = "import ent\n\n@ent.node('WRONG.id')\ndef run(inp):\n    return inp\n"
    node = _node(tmp_path, "mod.py::run", py)
    with pytest.raises(EntrypointDrift):
        resolve_entrypoint(node, tmp_path)


def test_extractor_reports_entrypoint_drift(tmp_path: Path) -> None:
    py = "import ent\n\n@ent.node('WRONG.id')\ndef run(inp):\n    return inp\n"
    _node(tmp_path, "mod.py::run", py)
    result = extract(tmp_path)
    assert not result.ok
    assert any("entrypoint drift" in e for e in result.errors)


def test_extractor_proposes_entrypoint_for_decorated_node() -> None:
    # llm.gateway has @ent.node but no contract.entrypoint → proposal.
    result = extract(GREENFIELD)
    proposals = result.graph["proposedEntrypoints"]
    assert proposals.get("llm.gateway") == "src/gateway/client.py::complete"

"""interior.steps — ordered, OTel-GenAI-shaped, and hash-bound against rot.

Research rec B: keep the ordered-step display and the anti-rot binding, but
shape each step as an OTel GenAI span type (chat / execute_tool /
invoke_agent / embeddings / workflow) instead of a bespoke schema — so steps
interoperate with every trace backend, and `observability.spanName` doubles
as the step↔span link. The hash binding is the commercially proven Swimm
model: a step whose bound file changed is DRIFT, not decoration.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

import yaml  # noqa: E402

from ent.extractor import extract  # noqa: E402
from ent.validation import validate_root  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    dest = tmp_path / "refundly"
    shutil.copytree(REFUNDLY, dest)
    return dest


def _decide(project: Path) -> dict:
    return yaml.safe_load((project / "src/decide/entiendo.node.yaml").read_text())


def test_the_living_example_validates_and_reconciles(project: Path) -> None:
    steps = _decide(project)["interior"]["steps"]
    assert len(steps) == 6
    assert all(s["kind"] in {"chat", "execute_tool", "invoke_agent",
                             "embeddings", "workflow"} for s in steps)
    assert validate_root(project).ok
    assert extract(project).ok


def test_a_stale_hash_is_drift_with_the_fix_in_the_message(project: Path) -> None:
    """The anti-rot mechanism: edit the bound file → the step's story may no
    longer be true → reconciliation drift, naming the new hash so updating
    the step after re-reading the code is copy-paste."""
    agent = project / "src/decide/agent.py"
    agent.write_text(agent.read_text() + "\n# behaviour moved\n")
    ext = extract(project)
    assert not ext.ok
    msg = " ".join(ext.errors)
    assert "stale" in msg and "parse" in msg
    new_hash = hashlib.sha256(agent.read_bytes()).hexdigest()[:12]
    assert new_hash in msg                              # the remedy is in the error
    drift, structural = ext.partition_errors()
    assert any("stale" in d for d in drift)             # drift-class → soft-able
    assert not structural


def test_step_crossing_needs_a_declared_edge(project: Path) -> None:
    mpath = project / "src/decide/entiendo.node.yaml"
    doc = yaml.safe_load(mpath.read_text())
    doc["interior"]["steps"].append(
        {"name": "sneak", "kind": "execute_tool", "crosses": "refundly.ledger"})
    # ledger IS declared (writes) — fine. Now cross to something undeclared:
    doc["dependencies"]["calls"].remove("refundly.orders")
    mpath.write_text(yaml.safe_dump(doc, sort_keys=False))
    ext = extract(project)
    assert not ext.ok
    assert any("step" in e and "refundly.orders" in e for e in ext.errors)


def test_unknown_crossing_is_structural(project: Path) -> None:
    mpath = project / "src/decide/entiendo.node.yaml"
    doc = yaml.safe_load(mpath.read_text())
    doc["interior"]["steps"] = [
        {"name": "ghost", "kind": "execute_tool", "crosses": "refundly.nowhere"}]
    mpath.write_text(yaml.safe_dump(doc, sort_keys=False))
    ext = extract(project)
    drift, structural = ext.partition_errors()
    assert any("unknown node" in e for e in structural)


def test_bad_kind_fails_schema_validation(project: Path) -> None:
    mpath = project / "src/decide/entiendo.node.yaml"
    doc = yaml.safe_load(mpath.read_text())
    doc["interior"]["steps"] = [{"name": "x", "kind": "magic"}]
    mpath.write_text(yaml.safe_dump(doc, sort_keys=False))
    assert not validate_root(project).ok


def test_steps_render_in_the_window() -> None:
    html = (REPO_ROOT / "src/ent/universe.html").read_text()
    assert "How it works, in order" in html
    assert "cannot silently rot" in html
    # OTel kinds surface as plain words, not jargon
    for words in ("asks a model", "uses a tool", "hands off to an agent"):
        assert words in html

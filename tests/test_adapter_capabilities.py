"""Adapter capability manifests + per-edge resolution grading (research round 2).

The closed-world guarantee is only as complete as each adapter's resolver —
"verified, not inferred" collapses exactly where resolution is partial
(Python's getattr, JS dynamic import()). The honest answer is a capability
manifest per adapter and a resolution grade per edge, published in the graph
artifact itself: the holes are declared, machine-readably, never hidden.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import languages  # noqa: E402
from ent.extractor import extract  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"

GRADES = {"compiler", "ast", "regex-poc"}


def test_every_registered_adapter_declares_its_blind_spots() -> None:
    """An honest adapter is never omniscient: a known grade, a distinct
    evidence tag, and at least one named construct it cannot resolve."""
    assert languages.registered(), "at least python + typescript are built in"
    for ex in languages.registered():
        caps = ex.capabilities()
        assert caps.grade in GRADES, ex.name
        assert caps.evidenceTag, ex.name
        assert caps.cannotResolve, f"{ex.name} claims to see everything"
        if not caps.complete:
            # partial-grade adapters must not wear the complete-evidence tag
            assert caps.evidenceTag not in ("import", "span"), ex.name


def test_the_graph_publishes_the_capability_manifests() -> None:
    graph = extract(REFUNDLY).graph
    adapters = {a["language"]: a for a in graph["adapters"]}
    assert "python" in adapters and "typescript" in adapters
    assert adapters["python"]["grade"] == "ast"
    assert adapters["typescript"]["grade"] == "regex-poc"
    assert adapters["typescript"]["evidenceTag"] == "ts-poc"
    assert all(a["cannotResolve"] for a in graph["adapters"])


def test_python_import_edges_grade_complete() -> None:
    """The self-hosted repo's own map: AST-verified import edges are
    complete-grade (refundly's units talk through the agent runtime, so its
    edges verify by span, not import — the repo root is the import fixture)."""
    graph = extract(REPO_ROOT).graph
    imported = [e for e in graph["edges"] if "import" in e["verificationSource"]]
    assert imported, "the self-hosted map has AST-verified edges"
    assert all(e["resolution"] == "complete" for e in imported)


def test_declared_but_never_verified_edges_grade_none() -> None:
    graph = extract(REFUNDLY).graph
    bare = [e for e in graph["edges"]
            if e["declared"] and not e["verificationSource"]]
    assert all(e["resolution"] == "none" for e in bare)


def test_ts_poc_edges_grade_partial(tmp_path: Path) -> None:
    """A TS project resolved by the regex PoC: its edges are real but
    partial-grade — the graph says so per edge, not in a footnote."""
    root = tmp_path / "tsapp"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir(parents=True)
    (root / "a" / "main.ts").write_text("import { x } from '../b/lib'\n")
    (root / "b" / "lib.ts").write_text("export const x = 1\n")
    for unit, claim, deps in (("app.a", "a/main.ts", "\n  calls: [app.b]"),
                              ("app.b", "b/lib.ts", " {}")):
        d = root / Path(claim).parent
        (d / "entiendo.node.yaml").write_text(
            f"apiVersion: entiendo/v1\nkind: Node\nid: {unit}\n"
            f"name: {unit}\ntask: t.\nnodeKind: compute\ngroup: app\n"
            f"owner: t\nstatus: experimental\nclaims: [{claim}]\n"
            f"contract:\n  invariants: ['output != None']\n  sideEffects: none\n"
            f"evals:\n  tier0:\n    - type: invariant_check\n"
            f"dependencies:{deps}\n")
    ext = extract(root)
    assert ext.ok, ext.errors
    edge = next(e for e in ext.graph["edges"]
                if e["from"] == "app.a" and e["to"] == "app.b")
    assert edge["verificationSource"] == ["ts-poc"]
    assert edge["resolution"] == "partial"


def test_doctor_prints_the_honest_boundary() -> None:
    proc = subprocess.run([sys.executable, "-m", "ent.cli", "doctor"],
                          cwd=str(REFUNDLY), capture_output=True, text=True,
                          timeout=120)
    assert "language adapters (what the map cannot see)" in proc.stdout
    assert "regex-poc" in proc.stdout
    assert "getattr" in proc.stdout       # python's named holes are spelled out

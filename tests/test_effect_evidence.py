"""Evaluability as graded evidence, never a verified invariant (research rec D).

Rice's theorem: "this unit performs no I/O" is undecidable, and a dynamic
probe only sees executed branches — so the sandbox's audit-hook probe reports
containment EVIDENCE. One direction is sound and gates: an effect the probe
observed is an effect the unit can perform, so `sideEffects: none` plus an
observed effect is a demonstrably false contract → RED. The other direction
never gates: observing nothing yields "no effects observed under probe", an
evidence grade that is never promoted to a verified claim.

(This probe found a real one on landing: ent.surface declared `none` while
build_view shells out to git for the commit axis — now declared `external`.)
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent.manifest import find_node  # noqa: E402
from ent.sandbox import run_sandboxed  # noqa: E402


def _project(tmp_path: Path, side_effects: str, body: str) -> Path:
    root = tmp_path / "app"
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "thing.py").write_text(textwrap.dedent(body))
    (root / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\n"
        "kind: Node\n"
        "id: app.thing\n"
        "name: Thing\n"
        "task: Do the thing.\n"
        "nodeKind: compute\n"
        "group: app\n"
        "owner: tester\n"
        "status: experimental\n"
        "claims: [lib/thing.py]\n"
        "contract:\n"
        "  entrypoint: lib/thing.py::run\n"
        "  invariants: [\"output['ok'] == True\"]\n"
        f"  sideEffects: {side_effects}\n"
        "evals:\n"
        "  tier0:\n"
        "    - type: invariant_check\n"
        "    - {type: smoke, fixture: evals/app.thing/smoke.jsonl}\n")
    (root / "evals" / "app.thing").mkdir(parents=True)
    (root / "evals" / "app.thing" / "smoke.jsonl").write_text(
        '{"name": "runs", "input": {}}\n')
    return root


WRITER = """
    from pathlib import Path
    def run(payload):
        out = Path(__file__).resolve().parent / "dropped.txt"   # inside the project
        out.write_text("side effect")
        return {"ok": True}
"""

PURE = """
    def run(payload):
        return {"ok": True}
"""


def test_observed_effect_against_a_none_contract_is_red(tmp_path: Path) -> None:
    root = _project(tmp_path, "none", WRITER)
    result = run_sandboxed(root, find_node(root, "app.thing"), 0)
    assert result["verdict"] == "RED"
    probe = next(c for c in result["checks"] if c["type"] == "effect_probe")
    assert "sideEffects: none" in probe["detail"]
    assert "fs-write" in probe["detail"]
    assert "dropped.txt" in probe["detail"]            # the sample names the file


def test_a_declared_effect_is_evidence_not_failure(tmp_path: Path) -> None:
    root = _project(tmp_path, "writes", WRITER)
    result = run_sandboxed(root, find_node(root, "app.thing"), 0)
    assert result["verdict"] == "GREEN"
    assert result["effects"]["observed"] == ["fs-write"]
    assert result["effects"]["declared"] == "writes"


def test_observing_nothing_is_evidence_never_verification(tmp_path: Path) -> None:
    root = _project(tmp_path, "none", PURE)
    result = run_sandboxed(root, find_node(root, "app.thing"), 0)
    assert result["verdict"] == "GREEN"
    eff = result["effects"]
    assert eff["observed"] == []
    assert eff["grade"] == "probe"                     # a grade, not a proof
    assert "proves nothing" in eff["note"]             # Rice, stated in the artifact
    assert "verified" not in eff["note"]


def test_tmp_and_plane_writes_are_runtime_noise_not_effects(tmp_path: Path) -> None:
    """Scratch files in the OS tempdir and the plane's own eval journal are
    excluded — the probe reports the UNIT's effects on the world."""
    body = """
    import tempfile, os
    from pathlib import Path
    def run(payload):
        fd, p = tempfile.mkstemp()                     # tempdir: excluded
        os.close(fd); Path(p).unlink()
        return {"ok": True}
    """
    root = _project(tmp_path, "none", body)
    result = run_sandboxed(root, find_node(root, "app.thing"), 0)
    assert result["verdict"] == "GREEN"
    assert result["effects"]["observed"] == []

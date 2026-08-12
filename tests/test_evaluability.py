"""Evaluability grades — three states instead of one smear of UNTESTED red.

    ready                    takes values, no effects observed → only missing
                             golden rows: a data chore, not a design problem
    evaluable-after-refactor fuses I/O with logic (reads the clock, talks to
                             the world with no declared edge) → the law fires
                             at build time, before the code hardens
    interior                 documented but never contracted

Honesty: "ready" is graded EVIDENCE — `ready (probed)` / `ready (static)`,
never "verified". The probe only observes the paths it executes.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import evaluability  # noqa: E402
from ent.manifest import Node, discover, load  # noqa: E402

PURE = """
    def run(payload):
        return {"ok": True, "n": payload.get("n", 0) * 2}
"""

CLOCKED = """
    import datetime
    def run(payload):
        return {"ok": True, "at": datetime.datetime.now().isoformat()}
"""


def _manifest(uid: str, claims: list[str], *, entrypoint: str | None,
              side: str = "none", deps: str = "", tier1: str = "",
              fixture: bool = True) -> str:
    contract = f"contract:\n  invariants: [\"output['ok'] == True\"]\n  sideEffects: {side}\n"
    if entrypoint:
        contract += f"  entrypoint: {entrypoint}\n"
    evals = "evals:\n  tier0:\n    - type: invariant_check\n"
    if fixture:
        evals += f"    - {{type: smoke, fixture: evals/{uid}/smoke.jsonl}}\n"
    if tier1:
        evals += tier1
    return (f"apiVersion: entiendo/v1\nkind: Node\nid: {uid}\nname: {uid}\n"
            f"task: t.\nnodeKind: compute\ngroup: app\nowner: t\n"
            f"status: experimental\nclaims: [{', '.join(claims)}]\n"
            f"{contract}{evals}{deps}")


def _write_unit(root: Path, uid: str, body: str | None, manifest: str) -> None:
    d = root / uid.replace(".", "_")
    d.mkdir(parents=True, exist_ok=True)
    if body is not None:
        (root / "lib").mkdir(exist_ok=True)
        (root / "lib" / f"{uid.split('.')[-1]}.py").write_text(textwrap.dedent(body))
    (d / "entiendo.node.yaml").write_text(manifest)
    (root / "evals" / uid).mkdir(parents=True, exist_ok=True)
    (root / "evals" / uid / "smoke.jsonl").write_text('{"name": "s", "input": {"n": 1}}\n')


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "app"
    root.mkdir()
    _write_unit(root, "app.pure", PURE,
                _manifest("app.pure", ["lib/pure.py"], entrypoint="lib/pure.py::run"))
    _write_unit(root, "app.clocked", CLOCKED,
                _manifest("app.clocked", ["lib/clocked.py"], entrypoint="lib/clocked.py::run"))
    _write_unit(root, "app.effectful", PURE,
                _manifest("app.effectful", ["lib/effectful.py"],
                          entrypoint="lib/effectful.py::run", side="external"))
    _write_unit(root, "app.interior", PURE,
                _manifest("app.interior", ["lib/interior.py"], entrypoint=None))
    return root


def _grades(root: Path) -> dict:
    nodes = [Node.from_manifest(load(p), p) for p in discover(root)]
    return evaluability.grade_all(root, nodes)


def test_the_three_states(project: Path) -> None:
    g = _grades(project)
    assert g["app.pure"]["grade"] == "ready"
    assert g["app.clocked"]["grade"] == "evaluable-after-refactor"
    assert g["app.effectful"]["grade"] == "evaluable-after-refactor"
    assert g["app.interior"]["grade"] == "interior"


def test_ready_is_awaiting_goldens_not_untested(project: Path) -> None:
    """The ent-new complaint: a fresh unit is 'declared, ready, awaiting
    goldens' — a data chore, not a smear of red."""
    g = _grades(project)["app.pure"]
    assert g["awaiting"] == "goldens"
    assert g["label"] == "ready (probed) — awaiting goldens"


def test_refactor_findings_name_the_split(project: Path) -> None:
    g = _grades(project)
    clocked = " ".join(g["app.clocked"]["why"])
    assert "reads the clock" in clocked and "inject the time" in clocked
    effectful = " ".join(g["app.effectful"]["why"])
    assert "declared dependency" in effectful


def test_ready_is_evidence_never_verified(project: Path) -> None:
    """The honesty constraint: the probe only observes executed paths — the
    grade is `(probed)` or `(static)`, and the word 'verified' never appears."""
    for g in _grades(project).values():
        assert g["evidence"] in ("probed", "static")
        assert "verified" not in str(g).lower()


def test_probed_downgrades_to_static_without_fixtures(tmp_path: Path) -> None:
    root = tmp_path / "app"
    root.mkdir()
    _write_unit(root, "app.bare", PURE,
                _manifest("app.bare", ["lib/bare.py"],
                          entrypoint="lib/bare.py::run", fixture=False))
    (root / "evals" / "app.bare" / "smoke.jsonl").unlink()
    g = _grades(root)["app.bare"]
    assert g["grade"] == "ready" and g["evidence"] == "static"


def test_declared_writes_edge_keeps_ready(tmp_path: Path) -> None:
    """writes behind a DECLARED dependency is stub-able — still judgeable on
    data alone; only a write fused into the logic forces the refactor."""
    root = tmp_path / "app"
    root.mkdir()
    _write_unit(root, "app.st", PURE,
                _manifest("app.st", ["lib/st.py"], entrypoint="lib/st.py::run",
                          side="writes"))
    _write_unit(root, "app.wr", PURE,
                _manifest("app.wr", ["lib/wr.py"], entrypoint="lib/wr.py::run",
                          side="writes",
                          deps="dependencies:\n  writes: [app.st]\n"))
    g = _grades(root)
    assert g["app.wr"]["grade"] == "ready"
    assert g["app.st"]["grade"] == "evaluable-after-refactor"


def test_the_map_carries_the_grade_and_recolours_untested(project: Path) -> None:
    from ent.render import build_view
    view = build_view(project)
    by_id = {n["id"]: n for n in view["nodes"]}
    assert by_id["app.pure"]["evaluability"]["grade"] == "ready"
    # untested-but-ready is BLUE on the health lens, not grey
    assert by_id["app.interior"]["healthColour"] == "grey"
    ready_untested = [n for n in view["nodes"]
                      if n["health"] == "UNTESTED"
                      and n["evaluability"]["grade"] == "ready"]
    assert all(n["healthColour"] == "blue" for n in ready_untested)


def test_extract_fires_the_law_at_build_time(project: Path) -> None:
    proc = subprocess.run([sys.executable, "-m", "ent.cli", "extract"],
                          cwd=str(project), capture_output=True, text=True,
                          timeout=120)
    assert "evaluable only after a refactor" in proc.stdout
    assert "app.clocked" in proc.stdout

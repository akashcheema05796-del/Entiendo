"""Clock-dependency detectors (hardening Phase 3) — the four fixture components.

    pure        no clock anywhere                → both passes: time_pure
    direct      datetime.now() in the entrypoint → static AND dynamic catch it
    deep        clock two calls down a helper    → static catches transitively
    seasonal    `month == 12` branch             → THE case static cannot
                confirm and dynamic must: passes today, breaks at +180 days

Findings are component properties with evidence, never test failures.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent.detectors import time_dynamic, time_static  # noqa: E402
from ent.manifest import Node, discover, load  # noqa: E402

PURE = """
    def run(payload):
        return {"ok": True, "n": payload.get("n", 0) * 2}
"""

DIRECT = """
    import datetime
    def run(payload):
        return {"ok": True, "at": datetime.datetime.now().isoformat()}
"""

DEEP_ENTRY = """
    from lib.helper_mid import middle
    def run(payload):
        return {"ok": True, "stamp": middle()}
"""
DEEP_MID = """
    from lib.helper_deep import bottom
    def middle():
        return bottom()
"""
DEEP_BOTTOM = """
    import time
    def bottom():
        return time.time()
"""

SEASONAL = """
    import datetime
    def run(payload):
        # passes every non-December test run — the classic landmine
        if datetime.datetime.now().month == 12:
            return {"ok": True, "discount": 0.25}
        return {"ok": True, "discount": 0.0}
"""


def _unit(root: Path, uid: str, files: dict[str, str], entry: str) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body))
    claims = "".join(f"\n- {rel}" for rel in files)
    (root / f"{uid}.entiendo.node.yaml").rename if False else None
    mdir = root / uid.replace(".", "_")
    mdir.mkdir(exist_ok=True)
    (mdir / "entiendo.node.yaml").write_text(
        f"apiVersion: entiendo/v1\nkind: Node\nid: {uid}\nname: {uid}\n"
        f"task: t.\nnodeKind: compute\ngroup: app\nowner: t\n"
        f"status: experimental\nclaims:{claims}\n"
        f"contract:\n  entrypoint: {entry}\n  invariants: [\"output['ok'] == True\"]\n"
        f"  sideEffects: none\n"
        f"evals:\n  tier0:\n    - type: invariant_check\n"
        f"    - {{type: smoke, fixture: evals/{uid}/smoke.jsonl}}\n")
    (root / "evals" / uid).mkdir(parents=True, exist_ok=True)
    (root / "evals" / uid / "smoke.jsonl").write_text(
        '{"name": "smoke", "input": {"n": 3}}\n')


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "app"
    root.mkdir()
    _unit(root, "app.pure", {"lib/pure.py": PURE}, "lib/pure.py::run")
    _unit(root, "app.direct", {"lib/direct.py": DIRECT}, "lib/direct.py::run")
    _unit(root, "app.deep",
          {"lib/deep.py": DEEP_ENTRY, "lib/helper_mid.py": DEEP_MID,
           "lib/helper_deep.py": DEEP_BOTTOM},
          "lib/deep.py::run")
    _unit(root, "app.seasonal", {"lib/seasonal.py": SEASONAL}, "lib/seasonal.py::run")
    return root


def _nodes(root: Path) -> list[Node]:
    return [Node.from_manifest(load(p), p) for p in discover(root)]


# --------------------------------------------------------------------------- #
# static
# --------------------------------------------------------------------------- #

def test_static_catches_direct_deep_and_seasonal_but_not_pure(project: Path) -> None:
    report = time_static.analyze_units(project, _nodes(project))
    assert report["app.pure"]["time_pure"] is True
    assert report["app.direct"]["time_pure"] is False
    assert report["app.seasonal"]["time_pure"] is False
    assert report["app.deep"]["time_pure"] is False          # two calls down


def test_static_evidence_carries_file_line_and_chain(project: Path) -> None:
    report = time_static.analyze_units(project, _nodes(project))
    direct = " ".join(report["app.direct"]["findings"])
    assert "lib/direct.py:" in direct and "datetime.now" in direct
    deep = " ".join(report["app.deep"]["findings"])
    assert "lib/helper_deep.py:" in deep and "time.time" in deep
    assert "via" in deep                                     # the call chain named


def test_static_is_marked_static_never_confirmed(project: Path) -> None:
    report = time_static.analyze_units(project, _nodes(project))
    assert all(r["grade"] == "static" for r in report.values())


# --------------------------------------------------------------------------- #
# dynamic — the seasonal branch is the acceptance criterion
# --------------------------------------------------------------------------- #

def test_dynamic_confirms_all_impure_including_seasonal(project: Path) -> None:
    pytest.importorskip("time_machine")
    nodes = {n.id: n for n in _nodes(project)}

    pure = time_dynamic.probe_unit(nodes["app.pure"], project)
    assert pure["time_pure"] is True and pure["time_check"] == "complete"

    direct = time_dynamic.probe_unit(nodes["app.direct"], project)
    assert direct["time_pure"] is False

    seasonal = time_dynamic.probe_unit(nodes["app.seasonal"], project)
    assert seasonal["time_pure"] is False, (
        "the seasonal month==12 branch passes today — only a shifted clock "
        "exposes it; this is the whole point of the dynamic pass")
    # whichever shift landed in December is named as evidence
    assert any("month sweep" in f or "+180 days" in f or "+1 year" in f
               for f in seasonal["findings"])


def test_dynamic_without_fixtures_is_a_named_skip(project: Path, tmp_path: Path) -> None:
    nodes = {n.id: n for n in _nodes(project)}
    node = nodes["app.pure"]
    (project / "evals" / "app.pure" / "smoke.jsonl").unlink()
    result = time_dynamic.probe_unit(node, project)
    assert result["time_check"] == "skipped"
    assert "no smoke fixtures" in result["note"]

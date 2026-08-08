"""PLAN_v7 Phase 1 — payload v2: windows render from the page, never a server.

Every field the floating windows need rides in the embedded payload; secrets
never enter it; statistics are passed through verbatim (no invented p-values —
`significant` means the bootstrap CI excludes zero); a zero-spread golden set
is flagged in the PAYLOAD, not computed in JS.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import history  # noqa: E402
from ent.render import build_view, render_html  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"


@pytest.fixture()
def refundly(tmp_path: Path) -> Path:
    dest = tmp_path / "refundly"
    shutil.copytree(REFUNDLY, dest)
    return dest


def test_payload_v2_shape(refundly: Path) -> None:
    view = build_view(refundly)
    assert view["payloadVersion"] == 2
    unit = next(n for n in view["nodes"] if n["id"] == "refundly.decide")
    for key in ("id", "name", "nodeKind", "group", "owner", "status", "version",
                "claims", "invariants", "evals", "history", "neighbours", "budgets"):
        assert key in unit, key
    assert set(unit["evals"]) == {"tier0", "tier1", "tier2"}
    t0 = unit["evals"]["tier0"]
    assert t0["total"] >= 1 and 0 <= t0["passed"] <= t0["total"] and t0["lastRunIso"]
    assert set(unit["neighbours"]) == {"out", "in"}
    assert all(set(e) == {"id", "rel", "verified"} for e in unit["neighbours"]["out"])
    for dim in ("code", "composite"):
        assert unit["version"][dim]


def test_payload_omits_secret_values(tmp_path: Path) -> None:
    root = tmp_path / "app"
    (root / "cfg").mkdir(parents=True)
    (root / "cfg/settings.yaml").write_text("api_key: SUPERSECRETVALUE9\nretries: 3\n")
    (root / "cfg/entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: app.cfg\nname: cfg\n"
        "nodeKind: config\nowner: me\nclaims:\n  - cfg/settings.yaml\n"
        "contract:\n  sideEffects: none\n")
    html = render_html(build_view(root))
    assert "SUPERSECRETVALUE9" not in html      # values never reach the page


def test_payload_blessed_by_passthrough(refundly: Path) -> None:
    history.record(refundly, {"kind": "bless", "nodeId": "refundly.parse_email",
                              "blessedBy": None, "ts": "2026-08-07T00:00:00Z"})
    unit = next(n for n in build_view(refundly)["nodes"]
                if n["id"] == "refundly.parse_email")
    row = next(r for r in unit["history"] if r["summary"] == "bless")
    assert row["blessedBy"] is None             # verbatim: never defaulted


def test_payload_zero_spread_flagged(refundly: Path) -> None:
    evals = refundly / "entiendo/history/evals.jsonl"
    evals.parent.mkdir(parents=True, exist_ok=True)
    with evals.open("a") as fh:
        fh.write(json.dumps({"tier": 1, "nodeId": "refundly.gateway",
                             "verdict": "WITHIN_BAND", "mean": 1.0, "baseline": 1.0,
                             "spread": 0.0, "n": 3, "nRows": 4,
                             "ciLow": 0.0, "ciHigh": 0.0,
                             "verdictMethod": "paired-bootstrap"}) + "\n")
    unit = next(n for n in build_view(refundly)["nodes"]
                if n["id"] == "refundly.gateway")
    t1 = unit["evals"]["tier1"]
    assert t1["spread"] == 0.0
    assert "non-discriminating" in t1["verdictLabel"]
    assert t1["significant"] is False


def test_payload_unverified_edges(tmp_path: Path) -> None:
    root = tmp_path / "app"
    for rel, body in {"a/x.py": "x=1\n", "b/y.py": "y=1\n"}.items():
        p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(body)
    (root / "a/entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: m.a\nname: a\nnodeKind: compute\n"
        "owner: me\nclaims:\n  - a/x.py\ncontract:\n  sideEffects: none\n"
        "dependencies:\n  reads:\n    - m.b\n")
    (root / "b/entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\nkind: Node\nid: m.b\nname: b\nnodeKind: compute\n"
        "owner: me\nclaims:\n  - b/y.py\ncontract:\n  sideEffects: none\n")
    unit = next(n for n in build_view(root)["nodes"] if n["id"] == "m.a")
    assert unit["neighbours"]["out"] == [{"id": "m.b", "rel": "reads", "verified": False}]


def test_page_refuses_unknown_payload_version() -> None:
    html = (REPO_ROOT / "src/ent/universe.html").read_text()
    assert "payloadVersion !== 2" in html and "unsupported payload version" in html


# --------------------------------------------------------------------------- #
# Phase 2 — window layer (structural; behaviour in tests/frontend/)
# --------------------------------------------------------------------------- #

def test_universe_contains_window_layer() -> None:
    html = (REPO_ROOT / "src/ent/universe.html").read_text()
    assert "openWindow" in html and ".win {" in html and "className='win'" in html
    assert "WIN_CAP=6" in html                    # 7th window minimizes LRU
    assert "setPointerCapture" in html            # header drag, captured


def test_universe_tab_ids() -> None:
    """A window shows the unit from every angle. Tab ids are plain words now —
    'inside' (the parts it is made of) leads, because a unit was an opaque box
    until you could see within it."""
    html = (REPO_ROOT / "src/ent/universe.html").read_text()
    assert "'inside','identity','promises','checks','history','impact','steer'" \
        in html.replace('"', "'")


def test_universe_no_localstorage() -> None:
    # workspace persistence is Phase 4, ON DISK — never localStorage
    assert "localStorage" not in (REPO_ROOT / "src/ent/universe.html").read_text()


# --------------------------------------------------------------------------- #
# Phase 4 — workspace persistence (user state on disk, never graph state)
# --------------------------------------------------------------------------- #

def _ws(windows):
    return {"version": 1, "lens": "health", "pan": {"x": 10, "y": 20},
            "windows": windows}


def test_workspace_roundtrip(refundly: Path) -> None:
    from ent.server import handle_api
    ws = _ws([{"id": "refundly.decide", "x": 120, "y": 90,
               "tab": "evals", "minimized": False}])
    status, out = handle_api(refundly, "POST", "/api/workspace", ws)
    assert status == 200 and out["saved"]
    restored = build_view(refundly)["workspace"]
    assert restored["lens"] == "health" and restored["pan"] == {"x": 10, "y": 20}
    assert restored["windows"][0]["x"] == 120 and restored["windows"][0]["tab"] == "evals"


def test_workspace_rejects_unknown_node_ids(refundly: Path) -> None:
    (refundly / "entiendo").mkdir(exist_ok=True)
    (refundly / "entiendo/workspace.json").write_text(json.dumps(
        _ws([{"id": "refundly.decide", "x": 1, "y": 2, "tab": "manifest", "minimized": False},
             {"id": "deleted.ghost", "x": 3, "y": 4, "tab": "blast", "minimized": False}])))
    ws = build_view(refundly)["workspace"]
    assert [w["id"] for w in ws["windows"]] == ["refundly.decide"]   # ghost dropped, no crash


def test_workspace_bad_version_rejected(refundly: Path) -> None:
    from ent.server import handle_api
    status, out = handle_api(refundly, "POST", "/api/workspace", {"version": 9})
    assert status == 400


def test_workspace_does_not_touch_graph(refundly: Path) -> None:
    from ent.extractor import extract as _extract, write_artifacts
    from ent.server import handle_api
    write_artifacts(_extract(refundly), refundly)
    before = (refundly / "entiendo/graph.json").read_bytes()
    handle_api(refundly, "POST", "/api/workspace",
               _ws([{"id": "refundly.gateway", "x": 5, "y": 6, "tab": "blast",
                     "minimized": True}]))
    assert (refundly / "entiendo/graph.json").read_bytes() == before


# --------------------------------------------------------------------------- #
# Phase 6 — gate integrity: windows are a human DISPLAY surface
# --------------------------------------------------------------------------- #

V6_MCP_TOOLS = {"get_graph", "get_node_context", "run_eval", "get_blast_radius",
                "apply_edit", "revert_node", "retrofit_propose", "retrofit_accept",
                "validate_manifests", "await_steering", "post_verdict"}


def test_no_new_mcp_tools_in_v7() -> None:
    import re
    src = (REPO_ROOT / "src/ent/mcp_server.py").read_text()
    tools = set(re.findall(r"@app\.tool\(\)\s+(?:async\s+)?def\s+(\w+)", src))
    assert tools == V6_MCP_TOOLS      # windows are a human surface — no new tools


def test_windows_carry_no_bless_or_direct_write_affordance() -> None:
    html = (REPO_ROOT / "src/ent/universe.html").read_text()
    assert "/api/bless" not in html               # no bless endpoint exists at all
    # the page's only write endpoints remain the v6 set + workspace (user state)
    import re
    posts = set(re.findall(r"api\('POST','(/api/[^']+)'", html))
    for p in posts:
        assert p.startswith(("/api/steer", "/api/proposals/", "/api/node/",
                             "/api/workspace")), p


def test_bless_requires_human() -> None:
    # the interactive gate is enforced in the command (isatty, exit 3) and the
    # writer (identity required); both are behaviourally tested in
    # test_v3_blessedby.py. Here: assert the guards still exist verbatim.
    bless = (REPO_ROOT / "src/ent/commands/bless.py").read_text()
    assert "sys.stdin.isatty()" in bless and "return 3" in bless
    from ent.baselines import write_bless
    import pytest as _pytest
    with _pytest.raises(ValueError):
        write_bless(Path("/tmp"), "x.y", dataset_rel="d", sha="s", rows=1,
                    blessed_by="unknown", blessed_at="t")

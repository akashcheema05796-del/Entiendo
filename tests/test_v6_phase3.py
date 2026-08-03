"""PLAN_v6 Phase 3 — durability, severity exit codes, steering atomicity,
extractor blind spots.

3.1 history._append is durable + concurrency-safe: parallel writer processes
    never interleave, truncate, or duplicate `seq`; new events carry `v: 1`.
3.2 `ent ci` gains a tier1 stage on BLESSED goldens with the Phase 7 severity
    exit codes (0 pass · 1 REGRESSED · 2 ERROR · 4 UNSTABLE/DEGRADED), max
    across stages. Unblessed goldens are advisory and never block.
    (Blessing in these fixtures is `baselines.write_bless` writing a TEST
    fixture record — the real refundly goldens stay unblessed for Mehar.)
3.4 claim_next claims via O_CREAT|O_EXCL (exactly one concurrent consumer
    wins); post_verdict / propose_from_outcome are idempotent; the HTTP
    handler enforces an X-Ent-Csrf token on POSTs (pure check function);
    the server binds 127.0.0.1 only.
3.5 the extractor flags dynamic constructs it cannot see
    (possibleUndeclaredDynamicDep) and tags TS-PoC edge evidence "ts-poc".
"""

from __future__ import annotations

import json
import multiprocessing
import shutil
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import baselines, history, steering  # noqa: E402
from ent.ci import run_ci  # noqa: E402
from ent.evals.runner import run_tier1  # noqa: E402
from ent.extractor import extract  # noqa: E402
from ent.manifest import find_node  # noqa: E402
from ent.server import check_csrf, inject_csrf  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"
PARSE = "refundly.parse_email"
DATASET = "evals/refundly.parse_email/golden_v3.jsonl"


def _mkproject(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tmp_path


def _node_yaml(node_id: str, *, claims: list[str]) -> str:
    claims_yaml = "\n".join(f"  - {c}" for c in claims)
    return (f"apiVersion: entiendo/v1\nkind: Node\nid: {node_id}\nname: {node_id}\n"
            f"nodeKind: compute\nowner: me\nclaims:\n{claims_yaml}\n"
            "contract:\n  sideEffects: none\n")


# --------------------------------------------------------------------------- #
# 3.1 durable, concurrency-safe history append
# --------------------------------------------------------------------------- #

def _history_writer(args: tuple[str, int]) -> None:
    root, i = args
    history.record(Path(root), {"kind": "stress", "writer": i})


def test_concurrent_appends_never_interleave_or_duplicate_seq(tmp_path: Path) -> None:
    n = 24
    with multiprocessing.Pool(6) as pool:
        pool.map(_history_writer, [(str(tmp_path), i) for i in range(n)])
    events = history.read_events(tmp_path)          # would raise on a torn line
    assert len(events) == n
    assert sorted(e["seq"] for e in events) == list(range(n))   # unique, gapless
    assert all(e["v"] == 1 for e in events)                     # schema version


def test_new_events_carry_v1_and_readers_tolerate_absence(tmp_path: Path) -> None:
    path = tmp_path / "entiendo/history/events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"seq": 0, "kind": "old"}\n')   # pre-v6 event: no "v"
    ev = history.record(tmp_path, {"kind": "new"})
    assert ev["v"] == 1 and ev["seq"] == 1
    old, new = history.read_events(tmp_path)
    assert "v" not in old and new["v"] == 1


# --------------------------------------------------------------------------- #
# 3.2 tier1 CI stage + severity exit codes
# --------------------------------------------------------------------------- #

@pytest.fixture()
def refundly(tmp_path: Path) -> Path:
    dest = tmp_path / "refundly"
    shutil.copytree(REFUNDLY, dest)
    return dest


def _bless_fixture(root: Path) -> list[float]:
    """Flip the FIXTURE's parse_email golden to blessed and return its actual
    per-row scores. This writes a test record in a throwaway copy — it is NOT a
    real dataset blessing (those are Mehar's alone)."""
    manifest = root / "src/parse_email/entiendo.node.yaml"
    manifest.write_text(manifest.read_text().replace(
        "humanBlessed: false", "humanBlessed: true"))
    dataset = root / DATASET
    baselines.write_bless(
        root, PARSE, dataset_rel=DATASET, sha=baselines.dataset_sha256(dataset),
        rows=len(dataset.read_text().splitlines()),
        blessed_by="fixture@test.example", blessed_at="2026-08-03T00:00:00Z")
    result = run_tier1(find_node(root, PARSE), root)
    assert not result.advisory                       # blessing is now gating
    return result.stats["rowScores"]


def _seed_baseline(root: Path, row_scores: list[float]) -> None:
    baselines.write_baseline(root, PARSE, {
        "baseline": 0.7778, "metric": "exact_match", "minRuns": 1,
        "significance": 0.05, "rowScores": row_scores})


def _tier1(result) -> object:
    return next(s for s in result.stages if s.name == "tier1")


def test_clean_blessed_golden_exits_0(refundly: Path) -> None:
    actual = _bless_fixture(refundly)
    _seed_baseline(refundly, actual)                 # baseline == reality
    result = run_ci(refundly)
    assert _tier1(result).ok and result.exit_code == 0
    assert PARSE + ":WITHIN_BAND" in _tier1(result).detail


def test_regressed_blessed_golden_exits_1(refundly: Path) -> None:
    actual = _bless_fixture(refundly)
    _seed_baseline(refundly, [s + 0.5 for s in actual])   # every row regresses
    result = run_ci(refundly)
    stage = _tier1(result)
    assert not stage.ok and stage.exit_severity == 1
    assert result.exit_code == 1
    assert PARSE + ":REGRESSED" in stage.detail


def test_unstable_blessed_golden_exits_4(refundly: Path) -> None:
    _bless_fixture(refundly)
    _seed_baseline(refundly, [1.0] * 9)              # mixed diffs → CI straddles 0
    result = run_ci(refundly)
    stage = _tier1(result)
    assert not stage.ok and stage.exit_severity == 4
    assert result.exit_code == 4                     # UNSTABLE outranks pass, not RED
    assert PARSE + ":UNSTABLE" in stage.detail


def test_unblessed_golden_is_advisory_and_never_blocks(refundly: Path) -> None:
    # a regressed-looking baseline, but the dataset is NOT blessed
    _seed_baseline(refundly, [1.0] * 9)
    result = run_ci(refundly)
    stage = _tier1(result)
    assert stage.ok and stage.exit_severity == 0 and result.exit_code == 0
    assert "advisory" in stage.detail and "never blocks" in stage.detail


# --------------------------------------------------------------------------- #
# 3.4 steering atomicity + idempotence + CSRF
# --------------------------------------------------------------------------- #

def _claimer(root: str) -> str | None:
    req = steering.claim_next(Path(root))
    return req["id"] if req else None


def test_exactly_one_concurrent_consumer_wins_a_claim(tmp_path: Path) -> None:
    steering.enqueue(tmp_path, "some.unit", "do the thing")
    with multiprocessing.Pool(8) as pool:
        wins = pool.map(_claimer, [str(tmp_path)] * 8)
    assert sum(1 for w in wins if w is not None) == 1


def test_post_verdict_is_idempotent(tmp_path: Path) -> None:
    req = steering.enqueue(tmp_path, "some.unit", "x")
    first = steering.post_verdict(tmp_path, req["id"], {"status": "done"})
    assert first.get("duplicate") is None
    second = steering.post_verdict(tmp_path, req["id"], {"status": "OVERWRITE"})
    assert second == {"duplicate": True, "id": req["id"]}
    # the stored result is the FIRST post, untouched
    assert steering.result_for(tmp_path, req["id"])["outcome"] == {"status": "done"}


def test_propose_from_outcome_is_idempotent(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text("after\n")
    outcome = {"diffs": {"f.py": {"before": "before\n", "after": "after\n"}},
               "unit": "some.unit", "unifiedDiffs": {}}
    first = steering.propose_from_outcome(tmp_path, "steer-1", outcome)
    assert first["status"] == "awaiting-approval"
    events_after_first = len(history.read_events(tmp_path))
    # tree was reverted by the first call; a duplicate must not revert again
    (tmp_path / "f.py").write_text("moved-on\n")
    dup = steering.propose_from_outcome(tmp_path, "steer-1", outcome)
    assert dup == {"duplicate": True, "id": "steer-1"}
    assert (tmp_path / "f.py").read_text() == "moved-on\n"      # no second revert
    assert len(history.read_events(tmp_path)) == events_after_first  # no new event


def test_csrf_check_and_injection() -> None:
    assert check_csrf("tok-abc", "tok-abc")
    assert not check_csrf("wrong", "tok-abc")
    assert not check_csrf(None, "tok-abc")
    assert not check_csrf("", "tok-abc")
    html = inject_csrf("<html><head><title>x</title></head></html>", "tok-abc")
    assert '<meta name="ent-csrf" content="tok-abc">' in html
    assert 'window.__entCsrf="tok-abc"' in html


def test_server_binds_loopback_only() -> None:
    src = (REPO_ROOT / "src/ent/server.py").read_text()
    assert 'HTTPServer(("127.0.0.1", port)' in src   # never 0.0.0.0


def test_universe_api_helper_sends_csrf_header() -> None:
    html = (REPO_ROOT / "src/ent/universe.html").read_text()
    assert "X-Ent-Csrf" in html and "window.__entCsrf" in html


# --------------------------------------------------------------------------- #
# 3.5 extractor blind spots + ts-poc evidence grade
# --------------------------------------------------------------------------- #

def test_dynamic_constructs_are_flagged_not_failed(tmp_path: Path) -> None:
    root = _mkproject(tmp_path, {
        "a/dyn.py": ('import importlib\nimport subprocess\n'
                     'mod = importlib.import_module("plugins.x")\n'
                     'handler = getattr(mod, "handle")\n'),
        "b/clean.py": "x = 1\n",
        "a/entiendo.node.yaml": _node_yaml("a.dyn", claims=["a/dyn.py"]),
        "b/entiendo.node.yaml": _node_yaml("b.clean", claims=["b/clean.py"]),
    })
    result = extract(root)
    warns = result.graph["possibleUndeclaredDynamicDep"]
    patterns = {w["pattern"] for w in warns if w["node"] == "a.dyn"}
    assert {"importlib.import_module", "subprocess", "getattr-dispatch"} <= patterns
    assert all(w["file"] == "a/dyn.py" for w in warns if w["node"] == "a.dyn")
    assert not [w for w in warns if w["node"] == "b.clean"]
    # warnings are advisory: they contribute NO errors
    assert result.ok, result.errors


def test_ts_poc_edges_carry_their_own_evidence_grade(tmp_path: Path) -> None:
    root = _mkproject(tmp_path, {
        "a/index.ts": "import { thing } from '../b/thing';\nexport const a = thing;\n",
        "b/thing.ts": "export const thing = 1;\n",
        "a/entiendo.node.yaml": (_node_yaml("a.one", claims=["a/index.ts"])
                                 + "dependencies:\n  calls:\n    - b.two\n"),
        "b/entiendo.node.yaml": _node_yaml("b.two", claims=["b/thing.ts"]),
    })
    result = extract(root)
    edge = next(e for e in result.graph["edges"]
                if e["from"] == "a.one" and e["to"] == "b.two")
    assert edge["verificationSource"] == ["ts-poc"]   # a PoC's evidence, labeled
    assert "import" not in edge["verificationSource"]


def test_python_import_evidence_grade_unchanged(tmp_path: Path) -> None:
    root = _mkproject(tmp_path, {
        "a/one.py": "from b.two import thing\n",
        "b/two.py": "thing = 1\n",
        "a/entiendo.node.yaml": (_node_yaml("a.one", claims=["a/one.py"])
                                 + "dependencies:\n  calls:\n    - b.two\n"),
        "b/entiendo.node.yaml": _node_yaml("b.two", claims=["b/two.py"]),
    })
    result = extract(root)
    edge = next(e for e in result.graph["edges"]
                if e["from"] == "a.one" and e["to"] == "b.two")
    assert edge["verificationSource"] == ["import"]


def test_build_view_carries_blind_spots_to_the_dossier(tmp_path: Path) -> None:
    from ent.render import build_view
    root = _mkproject(tmp_path, {
        "a/dyn.py": "import subprocess\n",
        "a/entiendo.node.yaml": _node_yaml("a.dyn", claims=["a/dyn.py"]),
    })
    view = build_view(root)
    unit = next(n for n in view["nodes"] if n["id"] == "a.dyn")
    assert unit["blindSpots"] == [
        {"node": "a.dyn", "file": "a/dyn.py", "pattern": "subprocess"}]

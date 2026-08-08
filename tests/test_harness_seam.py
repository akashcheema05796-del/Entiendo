"""`contract.harness` — how a unit whose entrypoint isn't a one-arg function
gets evaluated.

tier0 calls `entrypoint(row["input"])`. Units whose real entrypoint takes
`(node, root)`, `(root, node_id)`, no arguments at all, or a class that must be
constructed first were therefore permanently UNTESTED — a hole in the map, not
a fact about the code. The harness adapts the call while the declared
entrypoint stays the single source of truth for what runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent.evals.runner import run_tier0  # noqa: E402
from ent.manifest import find_node  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def _project(tmp_path: Path, *, harness: str | None, invariants: list[str],
             entry_src: str, entry: str, rows: list[dict]) -> Path:
    import yaml

    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "unit.py").write_text(entry_src)
    contract = {"entrypoint": f"src/unit.py::{entry}", "invariants": invariants,
                "sideEffects": "none"}
    if harness is not None:
        contract["harness"] = harness
    (tmp_path / "src" / "entiendo.node.yaml").write_text(yaml.safe_dump({
        "apiVersion": "entiendo/v1", "kind": "Node", "id": "demo.unit",
        "name": "Demo", "task": "Demo.", "nodeKind": "compute", "group": "demo",
        "owner": "tester", "status": "experimental", "claims": ["src/unit.py"],
        "contract": contract,
        "evals": {"tier0": [{"type": "invariant_check"},
                            {"type": "smoke", "fixture": "evals/smoke.jsonl"}]},
        "observability": {"spanName": "demo.unit"},
    }, sort_keys=False))
    (tmp_path / "evals").mkdir(exist_ok=True)
    (tmp_path / "evals" / "smoke.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")
    return tmp_path


TWO_ARG = "def combine(a, b):\n    return {'sum': a + b}\n"
ZERO_ARG = "def constant():\n    return {'value': 7}\n"


def test_two_argument_entrypoint_runs_through_a_harness(tmp_path: Path) -> None:
    root = _project(
        tmp_path, harness="evals/h.py::call", invariants=["output['sum'] == 5"],
        entry_src=TWO_ARG, entry="combine",
        rows=[{"name": "adds", "input": {"a": 2, "b": 3}}])
    (root / "evals" / "h.py").write_text(
        "def call(row, ctx):\n"
        "    return ctx.entrypoint(row['input']['a'], row['input']['b'])\n")
    res = run_tier0(find_node(root, "demo.unit"), root)
    assert res.verdict == "GREEN", [c.detail for c in res.checks]


def test_zero_argument_entrypoint_runs_through_a_harness(tmp_path: Path) -> None:
    root = _project(
        tmp_path, harness="evals/h.py::call", invariants=["output['value'] == 7"],
        entry_src=ZERO_ARG, entry="constant", rows=[{"name": "constant", "input": {}}])
    (root / "evals" / "h.py").write_text("def call(row, ctx):\n    return ctx.entrypoint()\n")
    assert run_tier0(find_node(root, "demo.unit"), root).verdict == "GREEN"


def test_harness_receives_root_and_node(tmp_path: Path) -> None:
    root = _project(
        tmp_path, harness="evals/h.py::call",
        invariants=["output['unit'] == 'demo.unit'", "output['root_ok'] == True"],
        entry_src=TWO_ARG, entry="combine", rows=[{"name": "ctx", "input": {}}])
    (root / "evals" / "h.py").write_text(
        "def call(row, ctx):\n"
        "    return {'unit': ctx.node.id, 'root_ok': (ctx.root / 'src').is_dir()}\n")
    assert run_tier0(find_node(root, "demo.unit"), root).verdict == "GREEN"


def test_a_harness_that_breaks_the_unit_still_goes_red(tmp_path: Path) -> None:
    """The seam must not become a way to launder a failing unit."""
    root = _project(
        tmp_path, harness="evals/h.py::call", invariants=["output['sum'] == 5"],
        entry_src="def combine(a, b):\n    return {'sum': 999}\n", entry="combine",
        rows=[{"name": "adds", "input": {"a": 2, "b": 3}}])
    (root / "evals" / "h.py").write_text(
        "def call(row, ctx):\n"
        "    return ctx.entrypoint(row['input'].get('a', 0), row['input'].get('b', 0))\n")
    assert run_tier0(find_node(root, "demo.unit"), root).verdict == "RED"


def test_missing_harness_file_is_an_error_not_a_pass(tmp_path: Path) -> None:
    root = _project(
        tmp_path, harness="evals/nope.py::call", invariants=[],
        entry_src=TWO_ARG, entry="combine", rows=[{"name": "x", "input": {}}])
    res = run_tier0(find_node(root, "demo.unit"), root)
    assert res.verdict == "ERROR"
    assert any("harness" in (c.detail or "") for c in res.checks)


def test_without_a_harness_the_single_argument_call_is_unchanged(tmp_path: Path) -> None:
    root = _project(
        tmp_path, harness=None, invariants=["output['echo'] == 'hi'"],
        entry_src="def echo(payload):\n    return {'echo': payload['msg']}\n",
        entry="echo", rows=[{"name": "echo", "input": {"msg": "hi"}}])
    assert run_tier0(find_node(root, "demo.unit"), root).verdict == "GREEN"


# --------------------------------------------------------------------------- #
# the self-host units this unblocked
# --------------------------------------------------------------------------- #

def test_every_self_host_unit_is_runnable() -> None:
    """No unit of this repo may sit UNTESTED because of the call shape."""
    from ent.extractor import extract

    graph = extract(REPO_ROOT).graph
    untested = [n["id"] for n in graph["nodes"] if n.get("health") == "UNTESTED"]
    assert not untested, f"units with no runnable eval: {untested}"


def test_harness_is_not_claimed_by_any_unit() -> None:
    """Harnesses are test scaffolding: editing one must not move a composite
    fingerprint, so no unit may claim it."""
    import yaml

    for manifest in (REPO_ROOT / "units").glob("*/entiendo.node.yaml"):
        claims = yaml.safe_load(manifest.read_text()).get("claims", [])
        assert not any(c.startswith("evals/") for c in claims), manifest

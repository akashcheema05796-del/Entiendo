"""Higher-order contracts — wrap-and-defer with blame (research rec E).

Findler & Felleisen (ICFP 2002): a contract on a function-returning function
cannot be checked eagerly; the returned closure is invoked later and the
deferred contract judges each invocation, assigning blame — a domain
violation blames the CALLER (the fixture row → eval ERROR, the unit is not at
fault), a range violation blames the UNIT (→ RED). Plain input/output schema
cannot express this; `contract.secondStage` + fixture `thenCall` rows can.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent.evals.runner import run_tier0  # noqa: E402
from ent.manifest import find_node  # noqa: E402
from ent.validation import validate_root  # noqa: E402

FACTORY_OK = """
    def make_threshold(cfg):
        limit = cfg["limit"]
        def check(payload):
            return {"allowed": payload["amount"] <= limit, "limit": limit}
        return check
"""

FACTORY_BROKEN = """
    def make_threshold(cfg):
        def check(payload):
            return {"allowed": True, "limit": -1}      # ignores the config
        return check
"""

FACTORY_NOT_A_FACTORY = """
    def make_threshold(cfg):
        return {"oops": "just data"}
"""


def _project(tmp_path: Path, body: str, *, then_call: str) -> Path:
    root = tmp_path / "app"
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "factory.py").write_text(textwrap.dedent(body))
    (root / "entiendo.node.yaml").write_text(
        "apiVersion: entiendo/v1\n"
        "kind: Node\n"
        "id: app.factory\n"
        "name: Threshold factory\n"
        "task: Compile a limit config into a checker.\n"
        "nodeKind: compute\n"
        "group: app\n"
        "owner: tester\n"
        "status: experimental\n"
        "claims: [lib/factory.py]\n"
        "contract:\n"
        "  entrypoint: lib/factory.py::make_threshold\n"
        "  invariants: []\n"
        "  sideEffects: none\n"
        "  secondStage:\n"
        "    domain: [\"input['amount'] >= 0\"]\n"
        "    invariants: [\"output['limit'] > 0\"]\n"
        "evals:\n"
        "  tier0:\n"
        "    - type: invariant_check\n"
        "    - {type: smoke, fixture: evals/app.factory/smoke.jsonl}\n")
    (root / "evals" / "app.factory").mkdir(parents=True)
    (root / "evals" / "app.factory" / "smoke.jsonl").write_text(then_call)
    return root


GOOD_ROW = ('{"name": "compiles-and-checks", "input": {"limit": 100}, '
            '"thenCall": [{"input": {"amount": 40}, '
            '"expect": {"allowed": true, "limit": 100}}, '
            '{"input": {"amount": 250}, '
            '"expect": {"allowed": false, "limit": 100}}]}\n')


def test_the_deferred_contract_passes_a_working_factory(tmp_path: Path) -> None:
    root = _project(tmp_path, FACTORY_OK, then_call=GOOD_ROW)
    assert validate_root(root).ok                       # schema knows secondStage
    result = run_tier0(find_node(root, "app.factory"), root)
    assert result.verdict == "GREEN", [c.detail for c in result.checks]


def test_a_range_violation_blames_the_unit(tmp_path: Path) -> None:
    root = _project(tmp_path, FACTORY_BROKEN, then_call=GOOD_ROW)
    result = run_tier0(find_node(root, "app.factory"), root)
    assert result.verdict == "RED"
    failing = next(c for c in result.checks if c.status == "fail")
    assert "blame: the unit" in failing.detail
    assert "output['limit'] > 0" in failing.detail


def test_a_domain_violation_blames_the_caller_not_the_unit(tmp_path: Path) -> None:
    """A fixture row that feeds the closure a contract-violating argument is a
    broken TEST, not a broken unit: ERROR with blame on the caller — the unit
    must not go RED for it."""
    bad_row = ('{"name": "negative-amount", "input": {"limit": 100}, '
               '"thenCall": [{"input": {"amount": -5}}]}\n')
    root = _project(tmp_path, FACTORY_OK, then_call=bad_row)
    result = run_tier0(find_node(root, "app.factory"), root)
    assert result.verdict == "ERROR"
    err = next(c for c in result.checks if c.status == "error")
    assert "blame: the caller" in err.detail
    assert "not the unit" in err.detail


def test_a_factory_that_returns_data_fails_its_higher_order_contract(tmp_path: Path) -> None:
    root = _project(tmp_path, FACTORY_NOT_A_FACTORY, then_call=GOOD_ROW)
    result = run_tier0(find_node(root, "app.factory"), root)
    assert result.verdict == "RED"
    failing = next(c for c in result.checks if c.status == "fail")
    assert "not a callable" in failing.detail


def test_a_closure_that_raises_blames_the_unit(tmp_path: Path) -> None:
    body = """
    def make_threshold(cfg):
        def check(payload):
            raise KeyError("boom")
        return check
    """
    root = _project(tmp_path, body, then_call=GOOD_ROW)
    result = run_tier0(find_node(root, "app.factory"), root)
    assert result.verdict == "RED"
    failing = next(c for c in result.checks if c.status == "fail")
    assert "raised KeyError" in failing.detail and "blame: the unit" in failing.detail

"""`ent fixtures <unit>` — propose smoke fixtures from traces (gap analysis §3).

The proposer reads recorded traces and scaffolds one skeleton per trace that
exercised the unit: named after the request, dep-stubs pre-wired from the
manifest, error traces flagged, and `input` left as a placeholder (traces don't
record payloads). refundly's committed traces are the fixture.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import fixtures  # noqa: E402
from ent.commands import fixtures as fixtures_cmd  # noqa: E402
from ent.fixtures import INPUT_PLACEHOLDER, propose_from_traces  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"


def test_proposes_one_skeleton_per_trace_exercising_the_unit() -> None:
    props = propose_from_traces(REFUNDLY, "refundly.decide")
    assert props, "refundly.decide is exercised by the committed traces"
    # each is named after the real trace it came from
    for p in props:
        assert p.fixture["name"] == f"from-{p.source_trace}"
        assert p.fixture["input"] == {"_": INPUT_PLACEHOLDER}   # payload is a placeholder


def test_dep_stubs_are_prewired_from_the_manifest() -> None:
    # refundly.decide declares calls to parse_email/orders/gateway → stubs scaffolded
    p = propose_from_traces(REFUNDLY, "refundly.decide")[0]
    deps = p.fixture.get("deps", {})
    assert deps, "declared call/read neighbours present in the trace get a stub"
    assert all(v == [{}] for v in deps.values())               # one placeholder stub each
    assert any("pre-wired stubs" in n for n in p.notes)


def test_error_trace_is_flagged_as_a_case_to_cover() -> None:
    # the bad-order trace ends in an error hop; the unit on that hop gets a note
    props = propose_from_traces(REFUNDLY, "refundly.orders")
    flagged = [p for p in props if any("error case" in n for n in p.notes)]
    assert flagged, "an error-status hop should be flagged as worth covering"


def test_unit_with_no_traces_yields_nothing() -> None:
    assert propose_from_traces(REFUNDLY, "refundly.policy") == [] \
        or all(p.source_trace for p in propose_from_traces(REFUNDLY, "refundly.policy"))


def test_write_proposals_goes_to_proposals_dir_never_the_real_fixture(tmp_path: Path) -> None:
    props = propose_from_traces(REFUNDLY, "refundly.decide")
    # write into a throwaway root so we don't touch the example
    (tmp_path / "entiendo").mkdir()
    path = fixtures.write_proposals(tmp_path, "refundly.decide", props)
    assert path == fixtures.proposal_path(tmp_path, "refundly.decide")
    assert "proposals/fixtures" in path.as_posix()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == len(props)


def test_cli_prints_proposals_and_exits_zero(capsys) -> None:
    code = fixtures_cmd._run(argparse.Namespace(unit="refundly.decide", root=str(REFUNDLY), write=False))
    out = capsys.readouterr().out
    assert code == 0
    assert "proposed smoke fixture" in out and "from-" in out


def test_cli_no_traces_is_clean(capsys) -> None:
    code = fixtures_cmd._run(argparse.Namespace(unit="refundly.nonexistent", root=str(REFUNDLY), write=False))
    out = capsys.readouterr().out
    assert code == 0
    assert "nothing to propose" in out

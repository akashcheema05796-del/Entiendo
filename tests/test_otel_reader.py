"""The OTel GenAI span reader (research rec C).

Manual `record()` bookkeeping is replaced by reading the spans the market's
auto-instrumentation already emits: `gen_ai.usage.input_tokens/output_tokens`
and `gen_ai.request.model` / `gen_ai.response.model`. Read-only — the only
write is a trace event in the flight recorder — and the previously-dead
`tokensPerCall` budget field now gates `ent ci`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import history  # noqa: E402
from ent.ci import run_ci  # noqa: E402
from ent.otel import bind_spans, genai_hops, ingest, observed_models, read_otlp  # noqa: E402
from ent.manifest import Node, discover, load  # noqa: E402
from ent.render import _measured_budgets  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    dest = tmp_path / "refundly"
    shutil.copytree(REFUNDLY, dest)
    return dest


def _otlp(spans: list[dict]) -> dict:
    return {"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]}


def _span(name: str, sid: str, *, parent: str | None = None, trace: str = "t1",
          attrs: dict | None = None, ns: tuple[int, int] = (0, 5_000_000),
          error: bool = False) -> dict:
    a = [{"key": k,
          "value": ({"intValue": str(v)} if isinstance(v, int) else {"stringValue": v})}
         for k, v in (attrs or {}).items()]
    s = {"name": name, "spanId": sid, "traceId": trace,
         "startTimeUnixNano": str(ns[0]), "endTimeUnixNano": str(ns[1]),
         "attributes": a}
    if parent:
        s["parentSpanId"] = parent
    if error:
        s["status"] = {"code": 2}
    return s


# A realistic shape: the unit's own span (named by observability.spanName)
# with an auto-instrumented LLM call nested inside it — the nested span knows
# nothing about Entiendo; it carries only standard gen_ai attributes.
FIXTURE = _otlp([
    _span("refundly.decide", "aaa", ns=(0, 40_000_000)),
    _span("chat claude-sonnet-5", "bbb", parent="aaa", attrs={
        "gen_ai.request.model": "claude-sonnet-5",
        "gen_ai.response.model": "claude-sonnet-5-20260114",
        "gen_ai.usage.input_tokens": 900,
        "gen_ai.usage.output_tokens": 300,
    }),
    _span("chat claude-sonnet-5", "ccc", parent="aaa", attrs={
        "gen_ai.response.model": "claude-sonnet-5-20260114",
        "gen_ai.usage.input_tokens": 100,
        "gen_ai.usage.output_tokens": 50,
    }),
    # a span bound by explicit attribute rather than name
    _span("some-framework-name", "ddd", trace="t2", attrs={
        "entiendo.node_id": "refundly.parse_email",
        "gen_ai.usage.input_tokens": 10,
        "gen_ai.usage.output_tokens": 5,
    }),
    # noise: a span bound to no unit at all
    _span("db.query", "eee", trace="t2"),
])


def _nodes(root: Path) -> list[Node]:
    return [Node.from_manifest(load(p), p) for p in discover(root)]


def test_otlp_parsing_flattens_attributes(tmp_path: Path) -> None:
    f = tmp_path / "x.json"
    f.write_text(json.dumps(FIXTURE))
    spans = read_otlp(f)
    assert len(spans) == 5
    llm = next(s for s in spans if s.span_id == "bbb")
    assert llm.attrs["gen_ai.usage.input_tokens"] == 900       # int, not str
    assert llm.attrs["gen_ai.response.model"] == "claude-sonnet-5-20260114"
    assert next(s for s in spans if s.span_id == "aaa").duration_ms == 40.0


def test_nested_genai_spans_bind_to_the_enclosing_unit(project: Path, tmp_path: Path) -> None:
    f = tmp_path / "x.json"
    f.write_text(json.dumps(FIXTURE))
    binding = bind_spans(read_otlp(f), _nodes(project))
    assert binding["aaa"] == "refundly.decide"
    assert binding["bbb"] == "refundly.decide"     # inherited from parent
    assert binding["ddd"] == "refundly.parse_email"  # explicit attribute
    assert binding["eee"] is None                   # noise stays unbound


def test_usage_aggregates_per_unit_per_trace(project: Path, tmp_path: Path) -> None:
    f = tmp_path / "x.json"
    f.write_text(json.dumps(FIXTURE))
    by_trace = genai_hops(read_otlp(f), _nodes(project))
    decide = by_trace["t1"][0]
    assert decide["node"] == "refundly.decide"
    assert decide["tokens"] == 1350                # 900+300 + 100+50
    assert decide["observedModels"] == ["claude-sonnet-5-20260114"]
    assert decide["requestedModels"] == ["claude-sonnet-5"]
    assert decide["duration_ms"] == 40.0           # the unit span's own duration


def test_ingest_records_traces_and_only_traces(project: Path, tmp_path: Path) -> None:
    f = tmp_path / "x.json"
    f.write_text(json.dumps(FIXTURE))
    events_before = len(history.read_events(project))
    summary = ingest(project, f)
    assert summary["units"] == ["refundly.decide", "refundly.parse_email"]
    assert summary["traces"] == 2 and summary["unbound"] == 1
    new = history.read_events(project)[events_before:]
    assert all(e["kind"] == "trace" for e in new)   # nothing but trace events
    assert observed_models(project)["refundly.decide"] == ["claude-sonnet-5-20260114"]


def test_tokens_flow_into_measured_budgets(project: Path, tmp_path: Path) -> None:
    f = tmp_path / "x.json"
    f.write_text(json.dumps(FIXTURE))
    ingest(project, f)
    m = _measured_budgets(history.traces(project))["refundly.decide"]
    assert m["avgTokens"] == 1350.0 and m["maxTokens"] == 1350


def test_token_budget_now_gates_ci(project: Path, tmp_path: Path) -> None:
    """The research's 'dead schema field': tokensPerCall declared but never
    enforced. Declare a budget below observed usage → ent ci exits DEGRADED."""
    import yaml

    mpath = project / "src/decide/entiendo.node.yaml"
    doc = yaml.safe_load(mpath.read_text())
    doc["budgets"] = {"tokensPerCall": 1000}
    mpath.write_text(yaml.safe_dump(doc, sort_keys=False))

    f = tmp_path / "x.json"
    f.write_text(json.dumps(FIXTURE))
    ingest(project, f)

    res = run_ci(project)
    budget = next(s for s in res.stages if s.name == "budgets")
    assert not budget.ok
    assert budget.exit_severity == 4               # DEGRADED, not RED
    assert any("refundly.decide" in w and "1350" in w for w in budget.warnings)
    assert res.exit_code == 4


def test_within_budget_passes(project: Path, tmp_path: Path) -> None:
    import yaml

    mpath = project / "src/decide/entiendo.node.yaml"
    doc = yaml.safe_load(mpath.read_text())
    doc["budgets"] = {"tokensPerCall": 5000}
    mpath.write_text(yaml.safe_dump(doc, sort_keys=False))
    # refundly ships a DELIBERATE gateway cost overage (its showcase); raise
    # that budget in this copy so the stage isolates decide's token budget.
    gpath = project / "src/gateway/entiendo.node.yaml"
    gdoc = yaml.safe_load(gpath.read_text())
    gdoc.setdefault("budgets", {})["costPerCallUsd"] = 0.10
    gpath.write_text(yaml.safe_dump(gdoc, sort_keys=False))

    f = tmp_path / "x.json"
    f.write_text(json.dumps(FIXTURE))
    ingest(project, f)
    budget = next(s for s in run_ci(project).stages if s.name == "budgets")
    assert budget.ok, (budget.detail, budget.warnings)


def test_cli_command_prints_the_accounting(project: Path, tmp_path: Path) -> None:
    import subprocess
    import sys

    f = tmp_path / "x.json"
    f.write_text(json.dumps(FIXTURE))
    proc = subprocess.run(
        [sys.executable, "-m", "ent.cli", "otel", str(f)],
        cwd=str(project), capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "refundly.decide" in proc.stdout and "1350 tokens" in proc.stdout
    assert "claude-sonnet-5-20260114" in proc.stdout


def test_garbage_files_fail_loudly_not_silently(project: Path, tmp_path: Path) -> None:
    import subprocess
    import sys

    bad = tmp_path / "bad.json"
    bad.write_text("not json at all")
    proc = subprocess.run(
        [sys.executable, "-m", "ent.cli", "otel", str(bad)],
        cwd=str(project), capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2
    assert "could not parse" in proc.stdout

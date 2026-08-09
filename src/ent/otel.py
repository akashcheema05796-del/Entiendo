"""OTel GenAI span reader — metering without entering the request path.

Manual ``record(cost_usd=..., tokens=...)`` made the caller do the accounting,
which the market has moved past: OTel GenAI semantic conventions standardise
``gen_ai.usage.input_tokens`` / ``gen_ai.usage.output_tokens`` and
``gen_ai.request.model`` / ``gen_ai.response.model``, and auto-instrumentation
libraries (OpenLLMetry, OpenLIT) emit them from the app's existing SDK calls.

Entiendo READS those spans — from an OTLP/JSON export file — and folds them
into the flight recorder as ordinary trace events. No proxy, no gateway, no
seat in the request path: the app (or its instrumentation library) produced
the spans; we only account for them (Invariant 2).

Span → unit binding, in priority order:
  1. an ``entiendo.node_id`` attribute on the span or an ancestor,
  2. span name equal to a unit's ``observability.spanName``.
GenAI usage on a span with no binding of its own rolls up to the nearest
bound ancestor, which is how auto-instrumented LLM calls nested inside an
``@ent.node()`` function attach to that unit.

Everything here is stdlib: OTLP/JSON is plain JSON with a list-of-{key,value}
attribute encoding. Parsed leniently — a span we cannot read is skipped, not
fatal — but token/model extraction itself is exact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

NODE_ID_ATTR = "entiendo.node_id"
IN_TOK = "gen_ai.usage.input_tokens"
OUT_TOK = "gen_ai.usage.output_tokens"
REQ_MODEL = "gen_ai.request.model"
RESP_MODEL = "gen_ai.response.model"


@dataclass
class OSpan:
    """One span, attributes flattened to a plain dict."""

    name: str
    span_id: str
    parent_id: str | None
    trace_id: str
    duration_ms: float | None
    status: str                      # "ok" | "error"
    attrs: dict[str, Any] = field(default_factory=dict)


def _attr_value(v: dict[str, Any]) -> Any:
    """OTLP/JSON AnyValue → python. Unhandled kinds collapse to None."""
    if "stringValue" in v:
        return v["stringValue"]
    if "intValue" in v:
        return int(v["intValue"])            # OTLP encodes int64 as string
    if "doubleValue" in v:
        return float(v["doubleValue"])
    if "boolValue" in v:
        return bool(v["boolValue"])
    return None


def _flatten_attrs(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):                # already-flat form: tolerate it
        return dict(raw)
    out: dict[str, Any] = {}
    for entry in raw or []:
        key = entry.get("key")
        if key is not None:
            out[key] = _attr_value(entry.get("value") or {})
    return out


def read_otlp(path: Path) -> list[OSpan]:
    """Parse an OTLP/JSON export file into flat spans.

    Accepts the standard shape (``resourceSpans[].scopeSpans[].spans[]``) and,
    leniently, a bare ``{"spans": [...]}`` or a top-level list of spans.
    """
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_spans: list[dict[str, Any]] = []
    if isinstance(doc, list):
        raw_spans = doc
    elif "resourceSpans" in doc:
        for rs in doc.get("resourceSpans") or []:
            for ss in rs.get("scopeSpans") or rs.get("instrumentationLibrarySpans") or []:
                raw_spans.extend(ss.get("spans") or [])
    else:
        raw_spans = doc.get("spans") or []

    out: list[OSpan] = []
    for s in raw_spans:
        try:
            start, end = s.get("startTimeUnixNano"), s.get("endTimeUnixNano")
            duration = (round((int(end) - int(start)) / 1e6, 3)
                        if start is not None and end is not None else None)
            code = ((s.get("status") or {}).get("code"))
            status = "error" if code in (2, "STATUS_CODE_ERROR") else "ok"
            out.append(OSpan(
                name=s.get("name") or "",
                span_id=str(s.get("spanId") or ""),
                parent_id=(str(s["parentSpanId"]) if s.get("parentSpanId") else None),
                trace_id=str(s.get("traceId") or ""),
                duration_ms=duration,
                status=status,
                attrs=_flatten_attrs(s.get("attributes")),
            ))
        except (TypeError, ValueError, KeyError):
            continue                          # a malformed span is skipped, not fatal
    return out


def _span_names(nodes: list[Any]) -> dict[str, str]:
    """observability.spanName → unit id (defaults to the id itself)."""
    out: dict[str, str] = {}
    for n in nodes:
        raw = getattr(n, "raw", {}) or {}
        span = (raw.get("observability") or {}).get("spanName") or n.id
        out[span] = n.id
    return out


def bind_spans(spans: list[OSpan], nodes: list[Any]) -> dict[str, str | None]:
    """span_id → unit id (or None). Unbound spans inherit the nearest bound
    ancestor within their trace, so nested gen_ai calls attach to the unit
    whose execution contains them."""
    by_name = _span_names(nodes)
    by_id = {s.span_id: s for s in spans}
    direct: dict[str, str | None] = {}
    for s in spans:
        direct[s.span_id] = (s.attrs.get(NODE_ID_ATTR)
                             or by_name.get(s.name))

    resolved: dict[str, str | None] = {}

    def resolve(sid: str, hops: int = 0) -> str | None:
        if sid in resolved:
            return resolved[sid]
        if hops > 64:                          # cycle guard
            return None
        span = by_id.get(sid)
        if span is None:
            return None
        unit = direct.get(sid)
        if unit is None and span.parent_id:
            unit = resolve(span.parent_id, hops + 1)
        resolved[sid] = unit
        return unit

    for s in spans:
        resolve(s.span_id)
    return resolved


def genai_hops(spans: list[OSpan], nodes: list[Any]) -> dict[str, list[dict[str, Any]]]:
    """Aggregate spans into per-trace, per-unit hops carrying gen_ai usage.

    Returns {otlp_trace_id: [hop, ...]} — one hop per unit per trace: summed
    token usage across that unit's gen_ai calls, the observed response
    model(s), and the unit span's own duration and status when one exists.
    """
    binding = bind_spans(spans, nodes)
    by_name = _span_names(nodes)
    agg: dict[tuple[str, str], dict[str, Any]] = {}

    for s in spans:
        unit = binding.get(s.span_id)
        if unit is None:
            continue
        hop = agg.setdefault((s.trace_id, unit), {
            "node": unit, "duration_ms": None, "status": "ok",
            "tokens": None, "inputTokens": None, "outputTokens": None,
            "observedModels": [], "requestedModels": [],
        })
        # the unit's own execution span carries duration/status
        directly_bound = (s.attrs.get(NODE_ID_ATTR) == unit
                          or by_name.get(s.name) == unit)
        if directly_bound and s.duration_ms is not None:
            hop["duration_ms"] = max(hop["duration_ms"] or 0.0, s.duration_ms)
        if s.status == "error":
            hop["status"] = "error"
        # gen_ai usage, wherever it appears in the unit's subtree
        itok, otok = s.attrs.get(IN_TOK), s.attrs.get(OUT_TOK)
        if isinstance(itok, int):
            hop["inputTokens"] = (hop["inputTokens"] or 0) + itok
        if isinstance(otok, int):
            hop["outputTokens"] = (hop["outputTokens"] or 0) + otok
        rm = s.attrs.get(RESP_MODEL)
        if isinstance(rm, str) and rm and rm not in hop["observedModels"]:
            hop["observedModels"].append(rm)
        qm = s.attrs.get(REQ_MODEL)
        if isinstance(qm, str) and qm and qm not in hop["requestedModels"]:
            hop["requestedModels"].append(qm)

    by_trace: dict[str, list[dict[str, Any]]] = {}
    for (tid, _unit), hop in sorted(agg.items()):
        if hop["inputTokens"] is not None or hop["outputTokens"] is not None:
            hop["tokens"] = (hop["inputTokens"] or 0) + (hop["outputTokens"] or 0)
        by_trace.setdefault(tid, []).append(hop)
    return by_trace


def ingest(root: Path, path: Path) -> dict[str, Any]:
    """Read an OTLP/JSON export and fold gen_ai usage into the flight recorder.

    One trace event per OTLP trace id, hops per unit. Appending to history is
    the ONLY write this performs. Returns a summary the CLI prints.
    """
    from . import history
    from .manifest import Node, discover, load

    root = Path(root)
    nodes = [Node.from_manifest(load(p), p) for p in discover(root)]
    spans = read_otlp(path)
    binding = bind_spans(spans, nodes)
    by_trace = genai_hops(spans, nodes)

    for tid, trace_hops in by_trace.items():
        history.append_trace(root, trace_hops, trace_id=f"otel-{tid[:16]}")

    hops = [h for hs in by_trace.values() for h in hs]
    return {
        "spans": len(spans),
        "traces": len(by_trace),
        "units": sorted({h["node"] for h in hops}),
        "hops": hops,
        "unbound": len([s for s in spans if binding.get(s.span_id) is None]),
    }


def observed_models(root: Path) -> dict[str, list[str]]:
    """unit id → distinct gen_ai.response.model values seen in recorded traces.

    The raw material for model-drift verification: what the app ACTUALLY ran,
    per unit, regardless of what the manifest declares.
    """
    from . import history

    out: dict[str, list[str]] = {}
    for tr in history.traces(root):
        for hop in tr.get("hops", []):
            nid = hop.get("node")
            for m in hop.get("observedModels") or []:
                if nid and m not in out.setdefault(nid, []):
                    out[nid].append(m)
    return out

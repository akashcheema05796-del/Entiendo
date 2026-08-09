"""`ent otel <file>` — fold OTel GenAI spans into the flight recorder.

The read-only alternative to manual cost/token bookkeeping: the app (or an
auto-instrumentation library like OpenLLMetry/OpenLIT) exports OTLP/JSON
spans; this ingests the `gen_ai.*` usage and observed model identity per
unit. Nothing proxies, nothing sits in the request path.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "otel",
        help="[L3] ingest OTel GenAI spans (OTLP/JSON) — tokens + observed models per unit",
        description="Read gen_ai.usage.* and gen_ai.response.model from an "
                    "OTLP/JSON export and record them as trace events.",
    )
    p.add_argument("file", help="OTLP/JSON export file (resourceSpans[...] or {spans:[...]})")
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    from ..otel import ingest

    root = Path(args.root).resolve()
    path = Path(args.file)
    if not path.exists():
        print(f"ent otel: no such file: {path}")
        return 2

    try:
        summary = ingest(root, path)
    except ValueError as exc:                    # json.JSONDecodeError subclasses this
        print(f"ent otel: could not parse {path.name}: {exc}")
        return 2

    print(f"  {summary['spans']} span(s) read · {summary['traces']} trace(s) recorded"
          f" · {summary['unbound']} span(s) bound to no unit")
    for hop in summary["hops"]:
        toks = f"{hop['tokens']} tokens" if hop.get("tokens") is not None else "no usage"
        models = ", ".join(hop.get("observedModels") or []) or "—"
        print(f"  {hop['node']:32} {toks:>16}   model {models}")
    if not summary["hops"]:
        print("  no gen_ai usage attached to any unit — check observability.spanName "
              "bindings or add entiendo.node_id attributes")
    return 0

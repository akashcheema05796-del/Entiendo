"""`ent import-tests <path> [--method ast|collect|both]` (hardening Phase 4).

Mines an existing pytest suite for cases: AST first (never executes repo
code), pytest collection for coverage (module import only — sandbox for
untrusted repos). One JSON case file per source test module lands under
`entiendo/proposals/imported-tests/`, and the coverage line is ALWAYS
printed — extraction gaps are visible, never hidden.

Exit codes: 0 report produced · 2 path missing / collection failed.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from ..extract import static_ast


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "import-tests",
        help="[retrofit] extract test cases from an existing pytest suite",
        description="Extract parametrized cases from pytest tests into case files.",
    )
    p.add_argument("path", help="test file or directory to mine")
    p.add_argument("--method", choices=["ast", "collect", "both"], default="both")
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.set_defaults(handler=_run)


def _collect(path: Path) -> dict | None:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        out = tmp.name
    env = {**os.environ, "ENT_EXTRACT_OUT": out}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "-p", "ent.extract.collect_plugin", str(path)],
        capture_output=True, text=True, timeout=300, env=env)
    try:
        data = json.loads(Path(out).read_text())
    except (OSError, ValueError):
        data = None
    finally:
        Path(out).unlink(missing_ok=True)
    if data is None and proc.returncode not in (0, 5):
        return None
    return data or {"collected": 0, "cases": []}


def _run(args: argparse.Namespace) -> int:
    target = Path(args.path)
    if not target.exists():
        print(f"ent import-tests: no such path {target}")
        return 2

    ast_cases: list[dict] = []
    ast_skipped = 0
    if args.method in ("ast", "both"):
        for _file, result in static_ast.extract_path(target).items():
            ast_cases.extend(result["cases"])
            ast_skipped += result["skipped_non_literal"]

    collect_cases: list[dict] = []
    needs_harness: list[dict] = []
    collected_total = 0
    if args.method in ("collect", "both"):
        data = _collect(target)
        if data is None:
            print("ent import-tests: pytest collection failed — falling back to "
                  "AST results only (run with --method ast to silence)")
        else:
            collected_total = data["collected"]
            for entry in data["cases"]:
                (needs_harness if entry.get("not_extractable") else
                 collect_cases).append(entry)

    # merge: collection wins on duplicates (it has resolved values), AST fills
    # in modules collection could not import
    by_module: dict[str, list[dict]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for entry in [*collect_cases, *ast_cases]:
        key = (entry["source_test"].split("::")[0], entry["case_id"])
        if key in seen:
            continue
        seen.add(key)
        module = Path(entry["source_test"].split("::")[0]).stem
        by_module[module].append(entry)

    root = Path(args.root).resolve()
    out_dir = root / "entiendo" / "proposals" / "imported-tests"
    out_dir.mkdir(parents=True, exist_ok=True)
    for module, cases in sorted(by_module.items()):
        (out_dir / f"{module}.cases.json").write_text(
            json.dumps({"cases": cases}, indent=2, sort_keys=True) + "\n")

    total_extracted = sum(len(v) for v in by_module.values())
    denominator = collected_total or total_extracted + ast_skipped
    print(f"extracted {total_extracted} of {denominator} collected cases "
          f"(AST: {len(ast_cases)}, collection: {len(collect_cases)}); "
          f"{len(needs_harness)} flagged needs_harness, "
          f"{ast_skipped} non-literal skipped by AST")
    for entry in needs_harness:
        print(f"  needs_harness  {entry['source_test']} — {entry['reason']}")
    if by_module:
        print(f"case files: {out_dir.relative_to(root)}/<module>.cases.json")
    return 0

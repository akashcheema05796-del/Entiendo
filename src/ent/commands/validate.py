"""`ent validate` — L0. Validate node manifests against the schema.

Discovers every entiendo.node.yaml under the project root (or validates the
paths given), checks each against schemas/node.schema.json, and enforces the
semantic rules L0 owns: id uniqueness, $ref resolution, claim existence, and the
humanBlessed gate on tier1 golden sets. Reports everything wrong in one pass.

Exit codes:
  0  all manifests valid
  1  one or more validation failures
  2  environment problem (e.g. jsonschema / pyyaml not installed)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..validation import Report, validate_paths, validate_root


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "validate",
        help="[L0] validate node manifests against the schema",
        description="Validate every entiendo.node.yaml against the node schema.",
    )
    p.add_argument(
        "paths",
        nargs="*",
        help="specific manifests to validate (default: discover all under --root)",
    )
    p.add_argument(
        "--root",
        default=".",
        help="project root claim paths resolve against (default: current directory)",
    )
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()

    try:
        if args.paths:
            paths = [Path(p) for p in args.paths]
            report = validate_paths(paths, root=root)
        else:
            report = validate_root(root)
    except ModuleNotFoundError as exc:
        print(f"ent validate: missing dependency — {exc}. Try: pip install -e '.[dev]'")
        return 2

    _print_report(report)
    return 0 if report.ok else 1


def _print_report(report: Report) -> None:
    checked = len(report.results)

    for result in report.results:
        if result.ok:
            print(f"  ok    {result.path}")
        else:
            print(f"  FAIL  {result.path}")
            for err in result.errors:
                print(f"          - {err}")

    for err in report.cross_errors:
        print(f"  FAIL  {err}")

    print()
    if report.ok:
        print(f"✓ {checked} manifest(s) valid")
    else:
        nodes_failed = sum(1 for r in report.results if not r.ok)
        print(
            f"✗ {report.error_count} error(s) across "
            f"{nodes_failed} manifest(s)"
            + (f" + {len(report.cross_errors)} cross-file" if report.cross_errors else "")
        )

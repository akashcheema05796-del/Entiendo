"""`ent validate` — L0. Validate node manifests against the schema.

STUB. Wired but not implemented — Phase 1 (L0) fills this in.

Planned behaviour:
  - discover every entiendo.node.yaml under the project root
  - validate each against schemas/node.schema.json
  - fail with a specific, fast error naming the file + field on any violation
  - check id uniqueness and that referenced $ref schema files exist
"""

from __future__ import annotations

import argparse

from ._stub import not_implemented


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "validate",
        help="[L0] validate node manifests against the schema",
        description="Validate every entiendo.node.yaml against the node schema.",
    )
    p.add_argument(
        "paths",
        nargs="*",
        help="specific manifests to validate (default: discover all under cwd)",
    )
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    return not_implemented(
        command="validate",
        phase="Phase 1 (L0: Boundaries)",
        summary="Discover and validate every entiendo.node.yaml against "
        "schemas/node.schema.json.",
        acceptance="a repo with 3 hand-written manifests validates; a malformed one "
        "fails with a useful error.",
    )

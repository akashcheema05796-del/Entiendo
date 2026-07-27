"""`ent new` — unit birth, fixture-first (v3 Phase F, the law as a tool).

A unit is only valid if it can be *evaluated independently on given data*
(the law). So `ent new` refuses to scaffold one without the thing that makes it
evaluable: a task in one sentence, and one fixture → its expected output. Given
those, it writes a manifest, a code stub, and a reflex (tier0) smoke that is
GREEN from birth — the loop works before you write real logic.

    ent new refunds.decider --task "Decide refund vs deny for a support email" \\
            --fixture '{"orderId": "o1"}' --expect '{"decision": "refund"}'

Interactive (a TTY, no flags) prompts for the same three things. Without a
fixture → expected pair, it exits 1 and writes nothing.

Exit codes: 0 created · 1 refused (missing task/fixture) or target exists
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "new",
        help="scaffold a new unit — refuses without a task + one fixture -> expected",
        description="Fixture-first unit birth: task (one sentence) + one fixture -> expected. "
                    "No fixture pair, no unit (the law).",
    )
    p.add_argument("id", help="unit id, dotted: <group>.<name> (e.g. refunds.decider)")
    p.add_argument("--task", help="one sentence: what this unit is for")
    p.add_argument("--kind", default="compute",
                   choices=["compute", "state", "schema", "config", "external", "pipeline"])
    p.add_argument("--owner", default="TODO", help="the human accountable (never the AI)")
    p.add_argument("--fixture", help="one fixture INPUT as JSON, e.g. '{\"x\": 1}'")
    p.add_argument("--expect", help="the expected OUTPUT for that fixture as JSON")
    p.add_argument("--dir", help="directory for the unit (default: src/<name>)")
    p.add_argument("--root", default=".", help="project root (default: current directory)")
    p.set_defaults(handler=_run)


def _prompt(msg: str) -> str:
    try:
        return input(msg).strip()
    except EOFError:
        return ""


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if "." not in args.id:
        print("ent new: id must be dotted <group>.<name> (e.g. refunds.decider)")
        return 1
    name = args.id.split(".")[-1]

    task = args.task
    fixture_raw, expect_raw = args.fixture, args.expect
    # interactive fill-in only when attached to a terminal
    if sys.stdin.isatty():
        task = task or _prompt("task (one sentence — what is this unit for?): ")
        if fixture_raw is None:
            fixture_raw = _prompt("one fixture INPUT (JSON): ")
        if expect_raw is None:
            expect_raw = _prompt("its expected OUTPUT (JSON): ")

    # THE refusal — no task, or no fixture -> expected pair, no unit (the law).
    if not task:
        print("ent new: refused — a unit needs a one-sentence task. Nothing written.")
        return 1
    if not fixture_raw or not expect_raw:
        print("ent new: refused — a unit needs one fixture -> expected verdict "
              "(--fixture and --expect). A unit you cannot evaluate on given data "
              "is not a unit (the law). Nothing written.")
        return 1
    try:
        fixture = json.loads(fixture_raw)
        expect = json.loads(expect_raw)
    except json.JSONDecodeError as exc:
        print(f"ent new: --fixture/--expect must be valid JSON — {exc}")
        return 1

    unit_dir = Path(args.dir) if args.dir else Path("src") / name
    dest = root / unit_dir
    manifest_path = dest / "entiendo.node.yaml"
    if manifest_path.exists():
        print(f"ent new: {manifest_path.relative_to(root)} already exists — refusing to overwrite.")
        return 1

    dest.mkdir(parents=True, exist_ok=True)
    code_rel = (unit_dir / f"{name}.py").as_posix()
    fixture_rel = (Path("evals") / args.id / "smoke.jsonl").as_posix()

    # code stub — returns the fixture's expected output as a placeholder, so the
    # unit is GREEN from birth (replace the TODO with real logic).
    (root / code_rel).write_text(
        f'"""{args.id} — {task}"""\n\n'
        "import ent\n\n\n"
        f"@ent.node({args.id!r})\n"
        "def run(req):\n"
        f"    # TODO: implement. Placeholder returns the smoke fixture's expected\n"
        f"    # output so the unit is green from birth; the fixture defines 'done'.\n"
        f"    return {expect!r}\n",
        encoding="utf-8",
    )

    # the one fixture -> expected, seeded from the required pair
    (root / fixture_rel).parent.mkdir(parents=True, exist_ok=True)
    (root / fixture_rel).write_text(
        json.dumps({"name": "smoke", "input": fixture, "expect": expect}) + "\n", encoding="utf-8")

    # manifest — task first; a reflex smoke that references the fixture
    manifest_path.write_text(
        "apiVersion: entiendo/v1\n"
        "kind: Node\n"
        f"id: {args.id}\n"
        f"name: {name}\n"
        f"task: {json.dumps(task)}\n"
        f"nodeKind: {args.kind}\n"
        f"group: {args.id.split('.')[0]}\n"
        f"owner: {args.owner}\n"
        "status: experimental\n"
        f"claims:\n  - {code_rel}\n"
        "contract:\n"
        f"  entrypoint: {code_rel}::run\n"
        "  invariants: []\n"
        "  sideEffects: none\n"
        "evals:\n"
        "  tier0:\n"
        "    - type: invariant_check\n"
        f"    - {{type: smoke, fixture: {fixture_rel}}}\n"
        "observability:\n"
        f"  spanName: {args.id}\n",
        encoding="utf-8",
    )

    print(f"✓ created {args.id}")
    print(f"    task      {task}")
    print(f"    manifest  {manifest_path.relative_to(root)}")
    print(f"    code      {code_rel}   (replace the TODO with real logic)")
    print(f"    fixture   {fixture_rel}   (defines 'done')")
    print(f"  next: ent eval {args.id}   → GREEN from birth")
    return 0

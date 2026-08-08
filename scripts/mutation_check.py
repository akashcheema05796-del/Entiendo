"""Mutation proof: break each unit, confirm its eval goes RED, restore.

A GREEN that cannot go RED is decoration. Every new harness-backed eval must
catch a real behavioural regression in the code it claims to test.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# unit -> (file, find, replace) — each mutation breaks the BEHAVIOUR the
# invariant asserts, not the syntax.
MUTATIONS = {
    "ent.versioning": ("src/ent/version.py",
                       'version["composite"] = composite(version)',
                       'version["composite"] = composite(version)[:8]'),
    # a runner that rubber-stamps: invariant failures no longer fail the unit
    "ent.evalkit": ("src/ent/evals/runner.py",
                    'if not passed:\n                    checks.append(Check("invariant_check", "fail",',
                    'if False:\n                    checks.append(Check("invariant_check", "fail",'),
    "ent.trust": ("src/ent/baselines.py",
                  "def read_baseline(root: Path, node_id: str) -> dict[str, Any] | None:",
                  "def read_baseline(root: Path, node_id: str) -> dict[str, Any] | None:\n"
                  "    return {'baseline': 0.0, 'metric': 'exact_match'}"),
    "ent.history": ("src/ent/history.py", '"seq": seq, "v": 1', '"seq": seq, "v": 99'),
    "ent.observer": ("src/ent/instrument.py", "return fn(*args, **kwargs)",
                     "return None if False else _ENT_MUTANT(fn(*args, **kwargs))"),
    "ent.timetravel": ("src/ent/trajectory.py",
                       "def evaluate(rule: dict[str, Any], calls: list[str], registry: set[str]) -> tuple[bool, str]:",
                       "def evaluate(rule: dict[str, Any], calls: list[str], registry: set[str]) -> tuple[bool, str]:\n"
                       "    return False, 'mutant'"),
    "ent.bridge": ("src/ent/editloop.py",
                   "def check_boundary(node: Node, changed_paths: list[str], root: Path) -> BoundaryResult:",
                   "def check_boundary(node: Node, changed_paths: list[str], root: Path) -> BoundaryResult:\n"
                   "    return BoundaryResult(within_claims=False, outside=['mutant'])"),
    "ent.packaging": ("src/ent/__init__.py", 'return version("entiendo")',
                      'return "0+unknown"'),
    "ent.plugin": (".claude/hooks/enforce_claims.py",
                   "def _managed_root(start: Path) -> Path | None:",
                   "def _managed_root(start: Path) -> Path | None:\n    return None"),
}


def verdict(unit: str) -> str:
    out = subprocess.run(["ent", "eval", unit], cwd=ROOT, capture_output=True,
                         text=True, timeout=180).stdout
    for token in ("GREEN", "RED", "ERROR", "UNTESTED"):
        if f": {token}" in out:
            return token
    return "?"


def main() -> int:
    # instrument.py needs a helper for its mutation to be a real behaviour change
    bad = []
    for unit, (rel, find, repl) in MUTATIONS.items():
        path = ROOT / rel
        original = path.read_text()
        if find not in original:
            print(f"[skip] {unit}: anchor not found in {rel}")
            bad.append(unit)
            continue
        mutant = original.replace(find, repl, 1)
        if unit == "ent.observer":       # define the mutant transform
            mutant = mutant.replace("from __future__ import annotations",
                                    "from __future__ import annotations\n"
                                    "_ENT_MUTANT = lambda v: v + 1", 1)
        try:
            path.write_text(mutant)
            v = verdict(unit)
        finally:
            path.write_text(original)
        caught = v in ("RED", "ERROR")
        print(f"[{'ok ' if caught else 'WEAK'}] {unit}: mutated → {v}")
        if not caught:
            bad.append(unit)

    print()
    # ent.evalkit is self-referential: the mutation that disables invariant
    # ENFORCEMENT also disables the evaluation that would catch it. No invariant
    # can close that loop — the pytest suite does (that mutation fails
    # test_break_ranker_goes_red_with_real_numbers, test_edit_red_when_invariant_breaks
    # and test_packaged_entrypoint_rereads_the_file_between_runs).
    expected_weak = {"ent.evalkit"}
    unexpected = [u for u in bad if u not in expected_weak]
    if unexpected:
        print(f"EVALS THAT DID NOT CATCH THEIR MUTATION: {unexpected}")
        return 1
    if bad:
        print(f"self-referential, covered by pytest instead: {sorted(bad)}")
    print(f"{len(MUTATIONS) - len(bad)}/{len(MUTATIONS)} evals caught their mutation")
    return 0


sys.exit(main())

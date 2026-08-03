"""Sandboxed eval execution (PLAN_v6 1.1). Defense-in-depth over Phase 7 isolation.

Node entrypoints used to run in-process with no timeout and no resource limits
(V6_VERIFICATION V0.11) — a hostile or buggy `while True:` node hung the runner.
This wraps the *whole node eval* in a child process:

  - the child runs the exact same `run_tier0` / `run_tier1` code path (so the
    fixture-stub isolation, the restricted-AST invariants, and trajectory checks
    behave identically — this layer replaces nothing);
  - the parent enforces a **wall-clock timeout** (default 5s tier0 / 30s tier1,
    manifest-overridable via `evals.timeoutMs`) and kills the child on breach →
    ERROR verdict `TIER0_TIMEOUT <node>`;
  - on POSIX the child lowers `resource` rlimits before executing (address
    space, CPU, open files, processes); skipped gracefully where unsupported.

The sandbox is used by the CLI surfaces (`ent eval`, `ent ci`) — the places that
execute *arbitrary manifest-declared* entrypoints. Internal read paths
(`build_view`'s health colouring, `review_edit`'s post-edit rerun) and explicit
`entrypoint=` overrides (test harnesses passing closures) stay in-process, where
execution is same-repo code the caller already imports.

`ENT_SANDBOX=1` marks the child so a sandboxed eval never re-sandboxes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT_S = {0: 5.0, 1: 30.0}

# Child resource limits (POSIX). Address space 512 MiB, 30s CPU, modest fd/proc.
_LIMITS = {"AS": 512 * 1024 * 1024, "CPU": 30, "NOFILE": 256, "NPROC": 64}


def in_sandbox() -> bool:
    return os.environ.get("ENT_SANDBOX") == "1"


def timeout_for(node: Any, tier: int) -> float:
    """Manifest `evals.timeoutMs` override, else the tier default."""
    ms = (node.raw.get("evals", {}) or {}).get("timeoutMs")
    if ms is not None:
        try:
            return max(0.1, float(ms) / 1000.0)
        except (TypeError, ValueError):
            pass
    return DEFAULT_TIMEOUT_S[tier]


def _apply_rlimits() -> None:  # pragma: no cover - exercised in the child only
    try:
        import resource
    except ImportError:                    # Windows — skip gracefully
        return
    for name, value in _LIMITS.items():
        limit = getattr(resource, f"RLIMIT_{name}", None)
        if limit is None:
            continue
        try:
            soft, hard = resource.getrlimit(limit)
            cap = value if hard == resource.RLIM_INFINITY else min(value, hard)
            resource.setrlimit(limit, (cap, hard))
        except (ValueError, OSError):
            continue                       # never fail the eval over a limit we can't set


_CHILD_CODE = """
import json, sys
from pathlib import Path
from ent.sandbox import _apply_rlimits
_apply_rlimits()
from ent.manifest import find_node
from ent.evals.runner import run_tier0, run_tier1
req = json.load(sys.stdin)
node = find_node(Path(req["root"]), req["node_id"])
if node is None:
    print(json.dumps({"error": f"no node {req['node_id']!r}"})); raise SystemExit(0)
runner = run_tier1 if req["tier"] == 1 else run_tier0
print(json.dumps(runner(node, Path(req["root"])).as_dict()))
"""


def run_sandboxed(root: Path, node: Any, tier: int = 0) -> dict[str, Any]:
    """Run a node's eval in a bounded child. Returns the EvalResult dict.

    A timeout / crashed child maps to an ERROR verdict — the runner must never
    hang and never guess GREEN from a dead child.
    """
    from . import verdicts

    timeout_s = timeout_for(node, tier)
    env = {**os.environ, "ENT_SANDBOX": "1"}
    request = json.dumps({"root": str(Path(root).resolve()), "node_id": node.id, "tier": tier})

    popen_kwargs: dict[str, Any] = {}
    if os.name == "posix":
        popen_kwargs["preexec_fn"] = _apply_rlimits   # belt + braces: also pre-exec

    try:
        proc = subprocess.run(
            [sys.executable, "-c", _CHILD_CODE],
            input=request, capture_output=True, text=True,
            timeout=timeout_s, env=env, **popen_kwargs)
    except subprocess.TimeoutExpired:
        return {
            "node_id": node.id, "tier": tier, "verdict": verdicts.ERROR,
            "duration_ms": round(timeout_s * 1000, 3),
            "checks": [{"type": "sandbox", "status": "error",
                        "detail": f"TIER0_TIMEOUT {node.id}: exceeded {timeout_s:.1f}s "
                                  "wall clock — child killed (evals.timeoutMs overrides)"}],
            "stats": {}, "advisory": False,
        }

    if proc.returncode != 0 or not proc.stdout.strip():
        tail = (proc.stderr or "").strip().splitlines()[-1:] or ["no output"]
        return {
            "node_id": node.id, "tier": tier, "verdict": verdicts.ERROR,
            "duration_ms": 0.0,
            "checks": [{"type": "sandbox", "status": "error",
                        "detail": f"sandboxed eval crashed (exit {proc.returncode}): {tail[0]}"}],
            "stats": {}, "advisory": False,
        }
    return json.loads(proc.stdout)

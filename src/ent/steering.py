"""The Bridge (v3 Phase C) — steering requests from the Universe to the workload.

The operator clicks a unit in the Universe and states an intent; that becomes a
**steering request** the workload (Claude Code, running the `entiendo-operator`
skill) picks up, acts on, and posts a **verdict** back to. The transport is
deliberately boring and inspectable — plain files under `entiendo/steering/`,
no websockets, no broker:

    entiendo/steering/
      queue.jsonl              # append-only log of requests (one JSON per line)
      claimed/<id>             # marker: a workload has taken this request
      results/<id>.json        # the verdict the workload posted back

A request is *pending* if it is in the queue, not claimed, and not resulted.
`ent serve` streams `pending` + `results` to the UI (poll), so the bubble flips
to "queued" and then to the verdict without the operator touching a terminal.

Everything here is a pure function over `root` so it is unit-tested without a
transport (mirrors `server.handle_api` / `mcp_server`).
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

_DIR = "entiendo/steering"


def _root(root: Path) -> Path:
    return Path(root) / _DIR


def _ensure(root: Path) -> Path:
    d = _root(root)
    (d / "claimed").mkdir(parents=True, exist_ok=True)
    (d / "results").mkdir(parents=True, exist_ok=True)
    return d


def _now() -> float:
    return round(time.time(), 3)


def enqueue(root: Path, unit: str, instruction: str) -> dict[str, Any]:
    """Append a steering request. Returns the request (with its generated id)."""
    d = _ensure(root)
    request = {
        "id": "steer-" + uuid.uuid4().hex[:10],
        "unit": unit,
        "instruction": instruction,
        "status": "queued",
        "ts": _now(),
    }
    with (d / "queue.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(request) + "\n")
    return request


def _read_queue(root: Path) -> list[dict[str, Any]]:
    path = _root(root) / "queue.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _is_claimed(root: Path, rid: str) -> bool:
    return (_root(root) / "claimed" / rid).exists()


def _result_path(root: Path, rid: str) -> Path:
    return _root(root) / "results" / f"{rid}.json"


def pending(root: Path) -> list[dict[str, Any]]:
    """Requests in the queue that are neither claimed nor resulted, oldest first."""
    return [
        r for r in _read_queue(root)
        if not _is_claimed(root, r["id"]) and not _result_path(root, r["id"]).exists()
    ]


def claim_next(root: Path) -> dict[str, Any] | None:
    """Take the oldest pending request and mark it claimed. Returns it, or None.

    Claiming is a marker file so a second poller (or a repeated `await_steering`)
    does not hand out the same request twice.
    """
    for r in _read_queue(root):
        rid = r["id"]
        if _is_claimed(root, rid) or _result_path(root, rid).exists():
            continue
        _ensure(root)
        (_root(root) / "claimed" / rid).write_text(str(_now()), encoding="utf-8")
        return {**r, "status": "claimed"}
    return None


def await_steering(root: Path, timeout_s: float = 25.0, poll_interval: float = 0.5) -> dict[str, Any]:
    """Long-poll for the next request. Returns it, or {"status": "timeout"}.

    Bounded so an MCP call returns; the workload simply calls it again to keep the
    operator loop alive. `poll_interval` is small; tests call `claim_next` directly.
    """
    deadline = time.time() + max(0.0, timeout_s)
    while True:
        req = claim_next(root)
        if req is not None:
            return req
        if time.time() >= deadline:
            return {"status": "timeout"}
        time.sleep(poll_interval)


def post_verdict(root: Path, request_id: str, outcome: Any) -> dict[str, Any]:
    """Record the workload's result for a request. Returns the stored result."""
    _ensure(root)
    result = {"id": request_id, "outcome": outcome, "ts": _now()}
    _result_path(root, request_id).write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


def result_for(root: Path, request_id: str) -> dict[str, Any] | None:
    path = _result_path(root, request_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def results(root: Path) -> dict[str, Any]:
    """All posted results, keyed by request id."""
    d = _root(root) / "results"
    if not d.exists():
        return {}
    out = {}
    for p in sorted(d.glob("*.json")):
        out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    return out


def poll(root: Path) -> dict[str, Any]:
    """The UI's view of the bridge: what's pending + every posted result."""
    return {"pending": pending(root), "results": results(root)}


# --------------------------------------------------------------------------- #
# H0.3 — approval, for real. A gated unit's edit lands as a PROPOSAL: the diff
# is captured, the working tree is reverted to `before`, and approve re-applies
# the stored `after` (a boring stored-diff apply — no live-tree magic).
# --------------------------------------------------------------------------- #

from . import gitinfo, history  # noqa: E402


def _proposals_dir(root: Path) -> Path:
    d = _root(root) / "proposals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def propose_from_outcome(root: Path, request_id: str, outcome: dict[str, Any]) -> dict[str, Any]:
    """Turn an applied edit on a gated unit into a proposal.

    `outcome` is the `apply_edit` result (carrying diffs + verdicts + behaviour
    delta). The working tree is reverted to `before` for each changed file, so the
    gated change is NOT live until approved. Returns the stored proposal.
    """
    diffs = outcome.get("diffs", {}) or {}
    unit = (outcome.get("outcome", {}) or {}).get("nodeId") or outcome.get("unit")

    # revert the working tree to `before` — the gate holds the change back.
    for rel, d in diffs.items():
        (Path(root) / rel).write_text(d.get("before", ""), encoding="utf-8")

    proposal = {
        "id": request_id,
        "unit": unit,
        "status": "awaiting-approval",
        "files": diffs,                                  # {rel: {before, after}}
        "unifiedDiffs": outcome.get("unifiedDiffs", {}),
        "verdictBefore": outcome.get("verdictBefore"),
        "verdictAfter": outcome.get("verdictAfter"),
        "behaviourDelta": outcome.get("behaviourDelta"),
        "blast": (outcome.get("outcome", {}) or {}).get("blast"),
        "summary": outcome.get("summary"),
        "ts": _now(),
    }
    (_proposals_dir(root) / f"{request_id}.json").write_text(
        json.dumps(proposal, indent=2), encoding="utf-8")
    history.record(root, {"kind": "proposal", "event": "created", "nodeId": unit,
                          "proposalId": request_id, "ts": gitinfo.now_iso()})
    # the steering result points at the proposal so the dossier shows "awaiting"
    post_verdict(root, request_id, {"status": "awaiting-approval", "proposalId": request_id})
    return proposal


def proposals(root: Path) -> list[dict[str, Any]]:
    """All open proposals (awaiting approval), oldest first."""
    d = _root(root) / "proposals"
    if not d.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))]


def proposal_for(root: Path, request_id: str) -> dict[str, Any] | None:
    path = _root(root) / "proposals" / f"{request_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def approve(root: Path, request_id: str) -> dict[str, Any]:
    """Apply a proposal's stored `after` to the working tree (stored-diff apply)."""
    prop = proposal_for(root, request_id)
    if prop is None:
        return {"error": f"no proposal '{request_id}'"}
    applied = []
    for rel, d in (prop.get("files", {}) or {}).items():
        (Path(root) / rel).write_text(d.get("after", ""), encoding="utf-8")
        applied.append(rel)
    (_proposals_dir(root) / f"{request_id}.json").unlink(missing_ok=True)
    history.record(root, {"kind": "proposal", "event": "approved", "nodeId": prop.get("unit"),
                          "proposalId": request_id, "ts": gitinfo.now_iso()})
    return {"approved": request_id, "unit": prop.get("unit"),
            "applied": sorted(applied), "verdict": prop.get("verdictAfter")}


def reject(root: Path, request_id: str) -> dict[str, Any]:
    """Discard a proposal. The working tree is already at `before` (never applied)."""
    prop = proposal_for(root, request_id)
    if prop is None:
        return {"error": f"no proposal '{request_id}'"}
    (_proposals_dir(root) / f"{request_id}.json").unlink(missing_ok=True)
    history.record(root, {"kind": "proposal", "event": "rejected", "nodeId": prop.get("unit"),
                          "proposalId": request_id, "ts": gitinfo.now_iso()})
    return {"rejected": request_id, "unit": prop.get("unit")}

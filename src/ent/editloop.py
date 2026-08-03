"""L5 — The scoped edit loop (SPEC.md §6).

The manifest *is* the retrieval index. When a human picks a node to change,
Entiendo assembles a context window from the node alone:

  - this node's manifest (contract, deps, budgets)
  - this node's claimed files (bodies)
  - the CONTRACTS ONLY of immediate neighbours (not their bodies)
  - the last N eval results + current baseline

Everything else in the repo is excluded *by construction* — that is the whole
point: the AI edits through the node, not through the repo (Invariant 8).

Then an edit is reviewed: it must stay inside `claims` (touching anything else
needs an explicit boundary-change proposal), tier0 reruns for a pass/fail
verdict, the blast radius shows what downstream is now at risk, and the approval
gate decides whether it can merge or must await human sign-off.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import history, verdicts
from .evals.runner import run_tier0, run_tier1
from .extractor import extract
from .manifest import Node, discover, find_node, load
from .render import blast_radius, build_view


# --------------------------------------------------------------------------- #
# context assembly
# --------------------------------------------------------------------------- #

@dataclass
class Context:
    """The scoped context window for editing one node."""

    node_id: str
    manifest: dict[str, Any]
    claimed_files: dict[str, str]           # path -> body (the ONLY bodies loaded)
    neighbour_contracts: dict[str, Any]     # neighbour id -> contract (no bodies)
    recent_evals: list[dict[str, Any]]
    baselines: dict[str, float]
    budgets: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "nodeId": self.node_id,
            "manifest": self.manifest,
            "claimedFiles": self.claimed_files,
            "neighbourContracts": self.neighbour_contracts,
            "recentEvals": self.recent_evals,
            "baselines": self.baselines,
            "budgets": self.budgets,
        }


def _immediate_neighbours(node: Node, all_nodes: list[Node]) -> set[str]:
    """Nodes one hop away in either direction (declared deps + callers)."""
    deps = node.raw.get("dependencies", {}) or {}
    out: set[str] = set()
    for kind in ("calls", "reads", "writes", "config"):
        out.update(deps.get(kind) or [])
    # callers: any node that declares a dependency on this one
    for other in all_nodes:
        odeps = other.raw.get("dependencies", {}) or {}
        for kind in ("calls", "reads", "writes", "config"):
            if node.id in (odeps.get(kind) or []):
                out.add(other.id)
    out.discard(node.id)
    return out


def assemble_context(root: Path, node_id: str, *, last_n: int = 5) -> Context:
    """Assemble the scoped edit context for a node. Loads nothing outside it."""
    root = Path(root)
    node = find_node(root, node_id)
    if node is None:
        raise KeyError(f"no node with id '{node_id}' under {root}")

    all_nodes = [Node.from_manifest(load(p), p) for p in discover(root)]
    by_id = {n.id: n for n in all_nodes}

    # Claimed files — the only file bodies that enter the window.
    claimed_files: dict[str, str] = {}
    for claim in node.claims:
        path = root / claim
        if path.exists() and path.is_file():
            claimed_files[claim] = path.read_text()

    # Immediate neighbours — contracts only, never bodies.
    neighbour_contracts: dict[str, Any] = {}
    for nid in sorted(_immediate_neighbours(node, all_nodes)):
        neighbour = by_id.get(nid)
        if neighbour is not None:
            neighbour_contracts[nid] = neighbour.raw.get("contract", {})

    recent = [e for e in history.timeline(root, node_id) if e.get("kind") == "eval"][-last_n:]

    baselines: dict[str, float] = {}
    for entry in node.raw.get("evals", {}).get("tier1", []) or []:
        if "metric" in entry and "baseline" in entry:
            baselines[entry["metric"]] = entry["baseline"]

    return Context(
        node_id=node_id,
        manifest=node.raw,
        claimed_files=claimed_files,
        neighbour_contracts=neighbour_contracts,
        recent_evals=recent,
        baselines=baselines,
        budgets=node.raw.get("budgets", {}) or {},
    )


# --------------------------------------------------------------------------- #
# edit review
# --------------------------------------------------------------------------- #

@dataclass
class BoundaryResult:
    within_claims: bool
    inside: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)


def check_boundary(node: Node, changed_paths: list[str], root: Path) -> BoundaryResult:
    """Verify every changed path is claimed by this node (SPEC.md §6 step 3).

    Routed through the single claims authority (v6 1.4): realpath + repo
    containment + resolved-claim membership, so a symlink or `../` cannot slip
    past what used to be a string comparison.
    """
    from . import claims as claims_mod
    inside, violations = [], []
    for raw in changed_paths:
        rel = claims_mod.claimed_rel(root, node, raw)
        (inside.append(rel) if rel is not None
         else violations.append(_relativise(raw, root)))
    return BoundaryResult(not violations, sorted(inside), sorted(violations))


def _relativise(path_str: str, root: Path) -> str:
    p = Path(path_str)
    try:
        if p.is_absolute():
            return p.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return p.as_posix()
    return p.as_posix()


@dataclass
class EditOutcome:
    node_id: str
    boundary: BoundaryResult
    verdict: str                     # tier0 green/red after the edit
    checks: list[dict[str, Any]]
    blast: dict[str, Any]
    approval_required: bool
    status: str                      # ready-to-merge | awaiting-signoff | blocked:*

    def as_dict(self) -> dict[str, Any]:
        return {
            "nodeId": self.node_id,
            "boundary": {
                "withinClaims": self.boundary.within_claims,
                "inside": self.boundary.inside,
                "violations": self.boundary.violations,
            },
            "verdict": self.verdict,
            "checks": self.checks,
            "blast": self.blast,
            "approvalRequired": self.approval_required,
            "status": self.status,
        }


def review_edit(root: Path, node_id: str, changed_paths: list[str]) -> EditOutcome:
    """Review a proposed edit: boundary + tier0 rerun + blast radius + approval."""
    root = Path(root)
    node = find_node(root, node_id)
    if node is None:
        raise KeyError(f"no node with id '{node_id}' under {root}")

    boundary = check_boundary(node, changed_paths, root)
    result = run_tier0(node, root)
    blast = blast_radius(build_view(root), node_id)
    approval_required = bool(node.raw.get("approval", {}).get("required", False))

    if not boundary.within_claims:
        status = "blocked: boundary-change proposal required"
    elif result.verdict in ("RED", "ERROR"):
        status = f"blocked: tier0 {result.verdict.lower()}"
    elif approval_required:
        status = "awaiting-signoff"
    else:
        status = "ready-to-merge"

    return EditOutcome(
        node_id=node_id,
        boundary=boundary,
        verdict=result.verdict,
        checks=[{"type": c.type, "status": c.status, "detail": c.detail} for c in result.checks],
        blast=blast,
        approval_required=approval_required,
        status=status,
    )


# --------------------------------------------------------------------------- #
# H0.2 — diff + behaviour capture for the steer/approve review surface
# --------------------------------------------------------------------------- #

def unified_diff(path: str, before: str, after: str) -> str:
    """A unified diff for one claimed file (bounded — claims are small)."""
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}", n=3))


def golden_mean(node: Node, root: Path) -> dict[str, Any] | None:
    """The unit's current golden metric mean, or None if it has no runnable golden."""
    res = run_tier1(node, root)
    if res.verdict == verdicts.UNTESTED or not res.stats:
        return None
    return {"metric": res.stats.get("metric"), "mean": res.stats.get("mean")}


def behaviour_delta(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any] | None:
    """The spec §6 before/after behaviour diff: golden metric moved by how much."""
    if not before or not after or before.get("mean") is None or after.get("mean") is None:
        return None
    d = round(after["mean"] - before["mean"], 4)
    return {
        "metric": after.get("metric") or before.get("metric"),
        "before": before["mean"], "after": after["mean"], "delta": d,
        "verdict": "IMPROVED" if d > 0 else "REGRESSED" if d < 0 else "WITHIN_BAND",
    }

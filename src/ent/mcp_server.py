"""`ent mcp` — Entiendo as an MCP server (stdio) for Claude Code.

This inverts L5's original design: instead of Entiendo calling a model through
the Anthropic SDK (agent.py), the model — Claude Code — calls Entiendo. Claude
Code is the editing agent; these tools are how it sees and touches the system,
and the manifest remains the retrieval index (SPEC.md §6):

  - `get_graph`           the full render model: nodes, edges, health, versions
  - `get_node_context`    the SCOPED context for one node — its manifest, claimed
                          file bodies, neighbour CONTRACTS ONLY, recent evals.
                          This is the only sanctioned way to read code.
  - `apply_edit`          write new file contents for a node. Writes are confined
                          to the node's `claims` (violations are rejected, not
                          written); tier0 reruns; verdict + blast radius returned.
  - `run_eval`            tier0/tier1 on demand
  - `get_blast_radius`    downstream dependents of a node
  - `revert_node`         restore pre-edit backups for a node
  - `retrofit_propose`    infer node manifests for an unmanaged repo (staging)
  - `retrofit_accept`     accept one proposal into the real tree
  - `validate_manifests`  L0 validation report
  - `await_steering`      (the Bridge) block for the next operator steering request
  - `post_verdict`        (the Bridge) report a steering request's result back

Design guarantees (unchanged from the HTTP surface):
  - Read-only observer except `apply_edit` / `revert_node` / `retrofit_accept`,
    and `apply_edit` writes ONLY within the node's claims.
  - The project root is fixed at server startup (--root). Tools cannot be pointed
    at arbitrary filesystem paths by the model.
  - The `mcp` SDK is an optional extra ([mcp]); without it, `ent mcp` explains
    how to install it and exits — nothing else in the tool is affected.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .editloop import assemble_context, review_edit
from .evals.runner import run_tier0, run_tier1
from .manifest import find_node
from .render import blast_radius, build_view
from .server import _backup, _BACKUP_DIR  # reuse the same backup convention as `ent serve`
from .validation import validate_root
from . import retrofit as retrofit_mod
from . import steering


# --------------------------------------------------------------------------- #
# tool implementations — pure functions over a fixed root, unit-testable
# without an MCP transport (mirrors server.handle_api's design)
# --------------------------------------------------------------------------- #

def tool_get_graph(root: Path) -> dict[str, Any]:
    return build_view(root)


def tool_get_node_context(root: Path, node_id: str) -> dict[str, Any]:
    if find_node(root, node_id) is None:
        return {"error": f"no node '{node_id}'"}
    return assemble_context(root, node_id).as_dict()


def tool_run_eval(root: Path, node_id: str, tier: str = "0") -> dict[str, Any]:
    node = find_node(root, node_id)
    if node is None:
        return {"error": f"no node '{node_id}'"}
    runner = run_tier1 if str(tier) == "1" else run_tier0
    return runner(node, root).as_dict()


def tool_get_blast_radius(root: Path, node_id: str) -> dict[str, Any]:
    if find_node(root, node_id) is None:
        return {"error": f"no node '{node_id}'"}
    return blast_radius(build_view(root), node_id)


def tool_apply_edit(
    root: Path, node_id: str, summary: str, files: list[dict[str, str]]
) -> dict[str, Any]:
    """Write `files` ([{path, content}]) for `node_id`, confined to its claims.

    Out-of-claims paths are REJECTED (returned, never written) — touching a file
    outside `claims` requires a boundary-change proposal, exactly as in SPEC §6.
    tier0 reruns after the write; the outcome carries verdict, blast radius, and
    approval status. Pre-edit contents are backed up for `revert_node`.
    """
    node = find_node(root, node_id)
    if node is None:
        return {"error": f"no node '{node_id}'"}
    if not files:
        return {"error": "no files provided"}

    ctx = assemble_context(root, node_id)
    claims = set(ctx.claimed_files)  # relative posix paths, same shape agent.py used

    written: list[str] = []
    rejected: list[str] = []
    diffs: dict[str, dict[str, str]] = {}

    for entry in files:
        rel = Path(entry["path"]).as_posix()
        if rel not in claims:
            rejected.append(rel)
            continue
        before = ctx.claimed_files.get(rel, "")
        diffs[rel] = {"before": before, "after": entry["content"]}
        _backup(root, node_id, rel, before)
        target = Path(root) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(entry["content"])
        written.append(rel)

    if not written:
        return {
            "error": "every path was outside the node's claims — nothing written",
            "rejected": sorted(rejected),
            "hint": "propose a boundary change (edit the manifest's `claims`) "
                    "and get human sign-off instead of writing around the boundary",
        }

    outcome = review_edit(root, node_id, written)
    return {
        "summary": summary,
        "changed": sorted(written),
        "rejected": sorted(rejected),
        "diffs": diffs,
        "outcome": outcome.as_dict(),
    }


def tool_revert_node(root: Path, node_id: str) -> dict[str, Any]:
    backup_root = Path(root) / _BACKUP_DIR / node_id
    if not backup_root.exists():
        return {"error": "nothing to revert"}
    restored = []
    for backup in backup_root.rglob("*"):
        if backup.is_file():
            rel = backup.relative_to(backup_root)
            (Path(root) / rel).write_text(backup.read_text())
            restored.append(rel.as_posix())
            backup.unlink()
    node = find_node(root, node_id)
    verdict = run_tier0(node, root).verdict if node else "ERROR"
    return {"restored": sorted(restored), "verdict": verdict}


def tool_retrofit_propose(root: Path) -> dict[str, Any]:
    proposals = retrofit_mod.propose(root)
    staged = retrofit_mod.write_proposals(root, proposals)
    return {
        "staged": str(staged),
        "coverage": retrofit_mod.coverage(root, proposals),
        "proposals": [
            {
                "id": p.node_id,
                "kind": p.manifest["nodeKind"],
                "confidence": p.confidence,
                "files": list(p.manifest["claims"]),
                "notes": p.notes,
            }
            for p in proposals
        ],
    }


def tool_retrofit_accept(root: Path, node_id: str) -> dict[str, Any]:
    dest = retrofit_mod.accept(root, node_id)
    if dest is None:
        return {"error": f"no staged proposal '{node_id}'"}
    return {"accepted": node_id, "manifest": str(dest)}


def tool_validate_manifests(root: Path) -> dict[str, Any]:
    report = validate_root(root)
    return {"ok": report.ok, "report": str(report)}


# --------------------------------------------------------------------------- #
# the Bridge (Phase C): the operator loop's ends — pull a steering request from
# the Universe, and post the verdict back to it.
# --------------------------------------------------------------------------- #

def tool_await_steering(root: Path, timeout_s: float = 25.0) -> dict[str, Any]:
    """Block (bounded) for the next steering request the operator queued.

    Returns the request {id, unit, instruction, ...} or {"status": "timeout"}.
    The workload then reads the unit with `get_node_context`, edits it with
    `apply_edit`, and reports back with `post_verdict(request_id, outcome)`.
    """
    return steering.await_steering(root, timeout_s=timeout_s)


def tool_post_verdict(root: Path, request_id: str, outcome: Any) -> dict[str, Any]:
    """Write the result of a steering request back to the Universe (its dossier
    flips from 'queued' to this verdict). `outcome` is typically the `apply_edit`
    result (verdict, blast radius, approval status) or a short status string."""
    return steering.post_verdict(root, request_id, outcome)


# --------------------------------------------------------------------------- #
# MCP wiring (optional dependency)
# --------------------------------------------------------------------------- #

def serve_mcp(root: Path) -> None:  # pragma: no cover — transport glue only
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise SystemExit(
            "ent mcp: the `mcp` package is not installed.\n"
            "  pip install 'entiendo[mcp]'   (or: pip install mcp)"
        ) from exc

    root = Path(root).resolve()
    app = FastMCP("entiendo")

    @app.tool()
    def get_graph() -> str:
        """Full system map: nodes, edges, health verdicts, versions, coverage."""
        return json.dumps(tool_get_graph(root))

    @app.tool()
    def get_node_context(node_id: str) -> str:
        """Scoped context for one node: manifest, claimed file bodies, neighbour
        contracts only, recent eval results. The ONLY sanctioned way to read code."""
        return json.dumps(tool_get_node_context(root, node_id))

    @app.tool()
    def run_eval(node_id: str, tier: str = "0") -> str:
        """Run a node's evals. tier '0' = deterministic/fast, '1' = golden dataset."""
        return json.dumps(tool_run_eval(root, node_id, tier))

    @app.tool()
    def get_blast_radius(node_id: str) -> str:
        """Downstream dependents at risk if this node changes, ranked by coupling."""
        return json.dumps(tool_get_blast_radius(root, node_id))

    @app.tool()
    def apply_edit(node_id: str, summary: str, files: list[dict[str, str]]) -> str:
        """Write new full contents for files of this node ([{path, content}]).
        Paths outside the node's claims are rejected, never written. tier0 reruns
        automatically; the outcome includes verdict, blast radius, approval status."""
        return json.dumps(tool_apply_edit(root, node_id, summary, files))

    @app.tool()
    def revert_node(node_id: str) -> str:
        """Restore this node's files from pre-edit backups."""
        return json.dumps(tool_revert_node(root, node_id))

    @app.tool()
    def retrofit_propose() -> str:
        """Infer node manifests for an unmanaged repo. Proposals go to a staging
        area with confidence + notes; nothing touches the real tree."""
        return json.dumps(tool_retrofit_propose(root))

    @app.tool()
    def retrofit_accept(node_id: str) -> str:
        """Accept ONE staged retrofit proposal into the real tree. Requires the
        human to have reviewed it — never bulk-accept."""
        return json.dumps(tool_retrofit_accept(root, node_id))

    @app.tool()
    def validate_manifests() -> str:
        """L0 validation of all manifests against the schema."""
        return json.dumps(tool_validate_manifests(root))

    @app.tool()
    def await_steering(timeout_s: float = 25.0) -> str:
        """Block (bounded) for the next steering request the operator queued in the
        Universe. Returns {id, unit, instruction} or {"status":"timeout"}. This is
        the head of the operator loop: await_steering → get_node_context →
        apply_edit → post_verdict. Call it again after each request to keep looping."""
        return json.dumps(tool_await_steering(root, timeout_s))

    @app.tool()
    def post_verdict(request_id: str, outcome: str) -> str:
        """Report a steering request's result back to the Universe (its dossier flips
        from 'queued' to this verdict). Pass the `apply_edit` outcome JSON or a short
        status. Closes the loop for `request_id`."""
        try:
            parsed = json.loads(outcome)
        except (json.JSONDecodeError, TypeError):
            parsed = outcome
        return json.dumps(tool_post_verdict(root, request_id, parsed))

    app.run()  # stdio transport — what Claude Code expects for local servers

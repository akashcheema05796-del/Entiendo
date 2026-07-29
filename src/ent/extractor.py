"""L1 — Extractor / reconciler. The real anti-drift mechanism (Invariant 5).

Statically analyses each node's claimed source files, derives the *actual* import
edges between nodes, and reconciles them against the `dependencies` declared in
the manifests. Import extraction is per-language behind a small seam
(`ent.languages`) — Python and a TypeScript/JS spike today — so the reconciler
itself is language-neutral. It then emits two GENERATED artifacts:

  - entiendo/graph.json     the node topology + edges (declared / verified / drift)
  - entiendo/coverage.json  claimed vs unclaimed files; the coverage headline

Reconciliation is asymmetric on purpose:

  - An **undeclared** edge — reality imports something the manifest hides — is
    drift and fails the build (Invariant 5). This is the case the acceptance test
    exercises.
  - A **declared-but-unverified** edge — a `reads`/`writes`/`config`/external
    relationship that static import analysis can't see — is reported, not failed.
    Static analysis is only one evidence source; runtime spans (L2) add more.

Also hard-fails on structural problems: a file claimed by two nodes, or a
declared dependency on a node id that doesn't exist.

Output is deterministic (sorted, no timestamps) so the artifacts diff cleanly and
never churn — they are committed per commit and must not produce merge noise.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import languages
from .evals.entrypoint import entrypoint_spec, propose_entrypoint, scan_decorated
from .manifest import MANIFEST_FILENAME, _SKIP_DIRS, Node, discover, load

GRAPH_ARTIFACT = "entiendo/graph.json"
COVERAGE_ARTIFACT = "entiendo/coverage.json"
UNCLAIMED_LIST = "entiendo/unclaimed.txt"

# Manifest dependency buckets, in report order.
DECLARED_EDGE_KINDS = ("calls", "reads", "writes", "config")

# Reconciliation errors of this kind are *drift* — reality diverging from the
# declared graph (an undeclared edge, an interior tool with no declared edge).
# Drift is the migration-friction kind `ent extract --soft` downgrades to a
# warning. Everything else (double-claim, dependency on an unknown node,
# entrypoint drift) is structural and always fails.
DRIFT_PREFIX = "drift:"


# --------------------------------------------------------------------------- #
# result types
# --------------------------------------------------------------------------- #

@dataclass
class ExtractResult:
    graph: dict[str, Any]
    coverage: dict[str, Any]
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def partition_errors(self) -> tuple[list[str], list[str]]:
        """Split errors into (drift, structural).

        Drift — undeclared edges, interior tools with no declared edge — is what
        `ent extract --soft` reports as warnings for a repo mid-migration.
        Structural errors (double-claim, unknown-node dependency, entrypoint
        drift) are authoring bugs and fail the build even in soft mode.
        """
        drift = [e for e in self.errors if e.startswith(DRIFT_PREFIX)]
        structural = [e for e in self.errors if not e.startswith(DRIFT_PREFIX)]
        return drift, structural


def _norm(rel: str) -> str:
    """Normalise a repo-relative path to posix form for stable keys."""
    return Path(rel).as_posix()


def _rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


# --------------------------------------------------------------------------- #
# ownership + coverage
# --------------------------------------------------------------------------- #

def _load_nodes(root: Path) -> list[Node]:
    return [Node.from_manifest(load(p), p) for p in discover(root)]


def _ownership(nodes: list[Node]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Map claimed file → owning node id, and surface any double-claims."""
    claims_by_file: dict[str, list[str]] = {}
    for node in nodes:
        for claim in node.claims:
            claims_by_file.setdefault(_norm(claim), []).append(node.id)
    owner = {f: ids[0] for f, ids in claims_by_file.items()}
    doubles = [
        {"file": f, "nodes": sorted(set(ids))}
        for f, ids in sorted(claims_by_file.items())
        if len(set(ids)) > 1
    ]
    return owner, doubles


def _candidate_files(root: Path) -> list[str]:
    """The universe of files coverage is measured over.

    Everything under root except vendored/generated dirs, the entiendo/ artifact
    tree, dotfiles, and the manifests themselves.
    """
    out: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(root).parts
        if any(p in _SKIP_DIRS for p in parts):
            continue
        if parts and parts[0] == "entiendo":
            continue
        if any(p.startswith(".") for p in parts):
            continue
        if path.name == MANIFEST_FILENAME:
            continue
        out.append(_rel(path, root))
    return sorted(out)


def _unclaimed_patterns(root: Path) -> list[str]:
    """Globs for files intentionally not owned by a node (Invariant 4)."""
    listing = root / UNCLAIMED_LIST
    if not listing.exists():
        return []
    patterns = []
    for line in listing.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def _coverage(root: Path, owner: dict[str, str]) -> dict[str, Any]:
    candidates = _candidate_files(root)
    claimed = {f for f in candidates if f in owner}
    patterns = _unclaimed_patterns(root)
    acknowledged = {
        f for f in candidates
        if f not in claimed and any(fnmatch.fnmatch(f, pat) for pat in patterns)
    }
    unaccounted = [f for f in candidates if f not in claimed and f not in acknowledged]

    total = len(candidates)
    accounted = len(claimed) + len(acknowledged)
    return {
        "apiVersion": "entiendo/v1",
        "total": total,
        "claimedCount": len(claimed),
        "acknowledgedUnclaimedCount": len(acknowledged),
        "unaccountedCount": len(unaccounted),
        "coverage": round(accounted / total, 4) if total else 1.0,
        "claimed": sorted(claimed),
        "acknowledgedUnclaimed": sorted(acknowledged),
        "unaccounted": unaccounted,
    }


# --------------------------------------------------------------------------- #
# edges + reconciliation
# --------------------------------------------------------------------------- #

def _build_edges(
    nodes: list[Node],
    owner: dict[str, str],
    root: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    node_ids = {n.id for n in nodes}
    errors: list[str] = []
    pairs: dict[tuple[str, str], dict[str, Any]] = {}

    def edge(frm: str, to: str) -> dict[str, Any]:
        return pairs.setdefault(
            (frm, to),
            {"kinds": set(), "declared": False, "verified": False, "evidence": []},
        )

    # Declared edges from manifests.
    for node in nodes:
        deps = node.raw.get("dependencies", {}) or {}
        for kind in DECLARED_EDGE_KINDS:
            for target in deps.get(kind) or []:
                if target not in node_ids:
                    errors.append(
                        f"{node.id}: declares dependency on unknown node '{target}' "
                        f"({kind})"
                    )
                    continue
                e = edge(node.id, target)
                e["kinds"].add(kind)
                e["declared"] = True

    # Actual edges from static import analysis — per-language, through the seam
    # (languages.for_file). A file with no registered extractor is skipped; the
    # Python path is byte-for-byte the same as before the seam existed.
    for node in nodes:
        for claim in node.claims:
            file = root / claim
            if not file.exists():
                continue
            extractor = languages.for_file(file)
            if extractor is None:
                continue
            for imp in extractor.resolved_imports(file, root):
                target_node = owner.get(_rel(imp.target, root))
                if not target_node or target_node == node.id:
                    continue
                e = edge(node.id, target_node)
                e["verified"] = True
                e["evidence"].append(f"{claim} imports {imp.detail}")
                if not e["declared"]:
                    e["kinds"].add("calls")

    # Interior tool registry (Phase D §14.3): a tool that crosses a border must
    # have a matching DECLARED edge. An edge-crossing tool with no edge = drift.
    for node in nodes:
        for tool in (node.raw.get("interior", {}) or {}).get("tools", []) or []:
            crosses = tool.get("crosses")
            if not crosses:
                continue
            name = tool.get("name")
            if crosses not in node_ids:
                errors.append(
                    f"{node.id}: interior tool '{name}' crosses to unknown node '{crosses}'"
                )
                continue
            e = pairs.get((node.id, crosses))
            if e is None or not e["declared"]:
                errors.append(
                    f"{DRIFT_PREFIX} interior tool '{name}' of {node.id} crosses to {crosses} "
                    f"but no dependency edge is declared — add {crosses} to {node.id}'s "
                    f"dependencies, or remove the tool from the registry"
                )

    # Undeclared (drift) → hard failure.
    for (frm, to), e in sorted(pairs.items()):
        if e["verified"] and not e["declared"]:
            evidence = e["evidence"][0] if e["evidence"] else "static import"
            errors.append(
                f"{DRIFT_PREFIX} undeclared dependency {frm} -> {to} "
                f"(observed: {evidence}) — declare it in {frm}'s manifest or remove it"
            )

    edges = [
        {
            "from": frm,
            "to": to,
            "kinds": sorted(e["kinds"]),
            "declared": e["declared"],
            "verified": e["verified"],
            "evidence": sorted(set(e["evidence"])),
        }
        for (frm, to), e in sorted(pairs.items())
    ]
    return edges, errors


# --------------------------------------------------------------------------- #
# top level
# --------------------------------------------------------------------------- #

def _node_summary(node: Node) -> dict[str, Any]:
    raw = node.raw
    return {
        "id": node.id,
        "name": raw.get("name"),
        "nodeKind": node.node_kind,
        "group": raw.get("group"),
        "owner": raw.get("owner"),
        "status": raw.get("status", "active"),
        "claims": list(node.claims),
        "sideEffects": raw.get("contract", {}).get("sideEffects"),
        "spanName": raw.get("observability", {}).get("spanName"),
        "approvalRequired": bool(raw.get("approval", {}).get("required", False)),
    }


def extract(root: Path) -> ExtractResult:
    """Build the graph + coverage for a project and reconcile against reality."""
    root = Path(root).resolve()
    nodes = _load_nodes(root)

    owner, doubles = _ownership(nodes)
    edges, edge_errors = _build_edges(nodes, owner, root)
    coverage = _coverage(root, owner)

    errors: list[str] = []
    for d in doubles:
        errors.append(
            f"file '{d['file']}' is claimed by multiple nodes: {', '.join(d['nodes'])} "
            "— every file is claimed by exactly one node (Invariant 4)"
        )
    errors.extend(edge_errors)

    # Entrypoint cross-check (Phase 7 §1.2): drift is an error; a decorated node
    # with no entrypoint gets a proposed line so filling it in is copy-paste.
    proposals, entry_errors = _entrypoints(nodes, root)
    errors.extend(entry_errors)

    graph = {
        "apiVersion": "entiendo/v1",
        "nodes": [_node_summary(n) for n in sorted(nodes, key=lambda n: n.id)],
        "edges": edges,
        "doubleClaimed": doubles,
        "proposedEntrypoints": proposals,
    }
    return ExtractResult(graph=graph, coverage=coverage, errors=errors)


def _entrypoints(nodes: list[Node], root: Path) -> tuple[dict[str, str], list[str]]:
    proposals: dict[str, str] = {}
    errors: list[str] = []
    for node in nodes:
        spec = entrypoint_spec(node)
        if spec:
            path_str, _, func = spec.partition("::")
            target = root / path_str
            decorated = scan_decorated(target) if target.exists() else {}
            if func in decorated and decorated[func] != node.id:
                errors.append(
                    f"entrypoint drift: {node.id} entrypoint '{spec}' is decorated "
                    f"@ent.node('{decorated[func]}') — decorator and manifest disagree"
                )
        else:
            proposed = propose_entrypoint(node, root)
            if proposed:
                proposals[node.id] = proposed
    return proposals, errors


def write_artifacts(result: ExtractResult, root: Path) -> tuple[Path, Path]:
    """Write graph.json + coverage.json under entiendo/. Deterministic output."""
    root = Path(root).resolve()
    graph_path = root / GRAPH_ARTIFACT
    coverage_path = root / COVERAGE_ARTIFACT
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps(result.graph, indent=2, sort_keys=False) + "\n")
    coverage_path.write_text(json.dumps(result.coverage, indent=2, sort_keys=False) + "\n")
    return graph_path, coverage_path

"""L1 — Extractor / reconciler. The real anti-drift mechanism (Invariant 5).

Statically analyses each node's claimed Python files, derives the *actual*
import edges between nodes, and reconciles them against the `dependencies`
declared in the manifests. It then emits two GENERATED artifacts:

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

import ast
import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .evals.entrypoint import entrypoint_spec, propose_entrypoint, scan_decorated
from .manifest import MANIFEST_FILENAME, _SKIP_DIRS, Node, discover, load

GRAPH_ARTIFACT = "entiendo/graph.json"
COVERAGE_ARTIFACT = "entiendo/coverage.json"
UNCLAIMED_LIST = "entiendo/unclaimed.txt"

# Manifest dependency buckets, in report order.
DECLARED_EDGE_KINDS = ("calls", "reads", "writes", "config")


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
# static import analysis
# --------------------------------------------------------------------------- #

def _imports(file: Path) -> list[tuple[str, int]]:
    """Return (module, level) for every import in a Python file.

    `level` is the relative-import depth (0 = absolute). `module` may be '' for
    `from . import x`.
    """
    try:
        tree = ast.parse(file.read_text())
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return []
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend((alias.name, 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.append((node.module or "", node.level))
    return out


def _resolve_import(module: str, level: int, importing: Path, root: Path) -> Path | None:
    """Resolve an import to a file within the project, or None if external.

    Handles absolute (root-relative) and relative imports. Only intra-project
    files resolve; third-party packages return None and are ignored.
    """
    if level > 0:
        base = importing.parent
        for _ in range(level - 1):
            base = base.parent
    else:
        base = root
    parts = module.split(".") if module else []
    target = base.joinpath(*parts)
    for candidate in (target.with_suffix(".py"), target / "__init__.py"):
        if candidate.exists():
            return candidate.resolve()
    return None


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

    # Actual edges from static import analysis.
    for node in nodes:
        for claim in node.claims:
            file = root / claim
            if file.suffix != ".py" or not file.exists():
                continue
            for module, level in _imports(file):
                target_file = _resolve_import(module, level, file, root)
                if target_file is None:
                    continue
                target_node = owner.get(_rel(target_file, root))
                if not target_node or target_node == node.id:
                    continue
                e = edge(node.id, target_node)
                e["verified"] = True
                e["evidence"].append(f"{claim} imports {module or '.'}")
                if not e["declared"]:
                    e["kinds"].add("calls")

    # Undeclared (drift) → hard failure.
    for (frm, to), e in sorted(pairs.items()):
        if e["verified"] and not e["declared"]:
            evidence = e["evidence"][0] if e["evidence"] else "static import"
            errors.append(
                f"drift: undeclared dependency {frm} -> {to} "
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

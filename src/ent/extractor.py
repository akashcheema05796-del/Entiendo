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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import languages
from .evals.entrypoint import entrypoint_spec, propose_entrypoint, scan_decorated
from .manifest import Node, discover, iter_project_files, load
from .version import compute_version

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
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        # a symlink escaping the root resolves OUTSIDE it — identify the
        # entry by its in-tree name instead of crashing the reconciliation
        # (the walk already refuses to treat such entries as project files)
        return path.relative_to(root).as_posix()


# --------------------------------------------------------------------------- #
# ownership + coverage
# --------------------------------------------------------------------------- #

def _load_nodes(root: Path) -> list[Node]:
    return [Node.from_manifest(load(p), p) for p in discover(root)]


def _ownership(nodes: list[Node], root: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Map claimed file → owning node id, and surface any double-claims."""
    from . import claims as claims_mod
    claims_by_file: dict[str, list[str]] = {}
    for node in nodes:
        for claim in claims_mod.expand_claims(root, node.claims):
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
    return sorted(_rel(p, root) for p in iter_project_files(root) if p.is_file())


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
    observed: dict[tuple[str, str], Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    node_ids = {n.id for n in nodes}
    by_id = {n.id: n for n in nodes}
    errors: list[str] = []
    pairs: dict[tuple[str, str], dict[str, Any]] = {}

    def edge(frm: str, to: str) -> dict[str, Any]:
        return pairs.setdefault(
            (frm, to),
            {"kinds": set(), "declared": False, "verified": False, "evidence": [],
             "sources": set(), "observationCount": 0, "lastVerifiedAt": None},
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
    from . import claims as claims_mod
    for node in nodes:
        for claim in claims_mod.expand_claims(root, node.claims):
            file = root / claim
            if not file.exists():
                continue
            extractor = languages.for_file(file)
            if extractor is None:
                continue
            # v6 3.5, generalised by the capability manifest: each adapter
            # declares its own evidence tag, and partial-grade adapters
            # (regex PoCs) must not claim the complete-evidence tag "import" —
            # the renderer draws their edges declared-grade.
            source = extractor.capabilities().evidenceTag
            for imp in extractor.resolved_imports(file, root):
                target_node = owner.get(_rel(imp.target, root))
                if not target_node or target_node == node.id:
                    continue
                e = edge(node.id, target_node)
                e["verified"] = True
                e["sources"].add(source)
                e["evidence"].append(f"{claim} imports {imp.detail}")
                if not e["declared"]:
                    e["kinds"].add("calls")

    # Actual edges from recorded runtime spans (V1) — the runtime source. An
    # observed edge verifies a DECLARED edge; a stale observation (the caller's
    # code changed since it was recorded) does not verify — it expires until
    # re-observed. An observed-but-undeclared edge is drift, same as an import.
    for (frm, to), obs in (observed or {}).items():
        current = _composite_of(by_id.get(frm), root)
        fresh = obs.callerComposite is not None and obs.callerComposite == current
        e = pairs.get((frm, to))
        if e is None or not e["declared"]:
            if fresh:                                   # observed a call nobody declared
                e = edge(frm, to)
                e["verified"] = True
                e["sources"].add("span")
                errors.append(
                    f"{DRIFT_PREFIX} undeclared dependency {frm} -> {to} "
                    f"(observed: runtime span) — declare it in {frm}'s manifest or remove it")
            continue
        e["evidence"].append(f"observed in {obs.observationCount} trace(s)")
        if fresh:
            e["verified"] = True
            e["sources"].add("span")
            e["observationCount"] = obs.observationCount
            e["lastVerifiedAt"] = obs.lastVerifiedAt

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

    # Interior steps (research rec B): each step is shaped as an OTel GenAI
    # span type, and a step may bind itself to code by content hash — docs
    # that cannot rot (Swimm-style Verify). A stale hash is DRIFT: the code
    # moved and the step's story about it may no longer be true.
    import hashlib
    for node in nodes:
        for step in (node.raw.get("interior", {}) or {}).get("steps", []) or []:
            sname = step.get("name")
            crosses = step.get("crosses")
            if crosses and crosses not in node_ids:
                errors.append(
                    f"{node.id}: interior step '{sname}' crosses to unknown node '{crosses}'")
            elif crosses:
                e = pairs.get((node.id, crosses))
                if e is None or not e["declared"]:
                    errors.append(
                        f"{DRIFT_PREFIX} interior step '{sname}' of {node.id} crosses to "
                        f"{crosses} but no dependency edge is declared")
            bound = step.get("boundTo")
            if bound:
                target = root / bound["file"]
                if not target.is_file():
                    errors.append(
                        f"{node.id}: interior step '{sname}' is bound to missing file "
                        f"'{bound['file']}'")
                    continue
                actual = hashlib.sha256(target.read_bytes()).hexdigest()[:12]
                if actual != bound["hash"]:
                    errors.append(
                        f"{DRIFT_PREFIX} interior step '{sname}' of {node.id} is stale: "
                        f"{bound['file']} is now {actual}, step was written against "
                        f"{bound['hash']} — re-read the code, update the step, then set "
                        f"hash: {actual}")

    # Undeclared (drift) → hard failure.
    for (frm, to), e in sorted(pairs.items()):
        if e["verified"] and not e["declared"]:
            evidence = e["evidence"][0] if e["evidence"] else "static import"
            errors.append(
                f"{DRIFT_PREFIX} undeclared dependency {frm} -> {to} "
                f"(observed: {evidence}) — declare it in {frm}'s manifest or remove it"
            )

    # Per-edge resolution grade (research round 2): 'complete' when at least
    # one complete-evidence source backs it (real AST import or a runtime
    # span), 'partial' when only partial-grade adapters saw it (regex PoC —
    # an inference-shaped hole, surfaced not hidden), 'none' when declared
    # but never verified by anything.
    COMPLETE_SOURCES = {"import", "span"}
    edges = [
        {
            "from": frm,
            "to": to,
            "kinds": sorted(e["kinds"]),
            "declared": e["declared"],
            "verified": e["verified"],
            # tri-state metadata (V1): who verified it, how often, when last seen.
            "verificationSource": sorted(e["sources"]),
            "resolution": ("complete" if e["sources"] & COMPLETE_SOURCES
                           else "partial" if e["sources"] else "none"),
            "observationCount": e["observationCount"],
            "lastVerifiedAt": e["lastVerifiedAt"],
            "evidence": sorted(set(e["evidence"])),
        }
        for (frm, to), e in sorted(pairs.items())
    ]
    return edges, errors


# --------------------------------------------------------------------------- #
# blind spots (v6 3.5) — what static import analysis CANNOT see
# --------------------------------------------------------------------------- #

# Constructs the AST import walk is blind to: dynamic imports, string-keyed
# dispatch, and out-of-process / network calls. A hit is a WARNING, never an
# error — the point is honesty ("absence of an edge is not proof of no
# dependency"), not a new gate.
_DYNAMIC_DEP_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("importlib.import_module", re.compile(r"\bimportlib\.import_module\s*\(")),
    ("__import__", re.compile(r"\b__import__\s*\(")),
    ("getattr-dispatch", re.compile(r"\bgetattr\s*\([^)\n]*,\s*['\"]")),
    ("subprocess", re.compile(r"\bsubprocess\b")),
    ("requests", re.compile(r"\brequests\b")),
    ("httpx", re.compile(r"\bhttpx\b")),
    ("urllib", re.compile(r"\burllib\b")),
)


# The same honesty for TypeScript/JS claims (v7): dynamic imports, runtime
# requires, child processes, and network clients are all edges the regex
# import walk cannot see.
_JS_EXTS = {".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"}
_DYNAMIC_DEP_PATTERNS_JS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("dynamic-import", re.compile(r"\bimport\s*\(")),
    ("require", re.compile(r"\brequire\s*\(")),
    ("child_process", re.compile(r"\bchild_process\b|\bexecFile\b|\bspawn\s*\(")),
    ("network-client", re.compile(r"\bfetch\s*\(|\baxios\b|\bundici\b|\bWebSocket\b")),
)


def _dependency_cycles(node_ids: set[str], edges: list[dict[str, Any]]) -> list[list[str]]:
    """Strongly-connected components with >1 member (v7) — circular dependency
    groups. Tarjan, iterative. A cycle is a WARNING, not a failure: the map's
    job is to make the knot visible, not to forbid it."""
    adj: dict[str, list[str]] = {n: [] for n in node_ids}
    for e in edges:
        if e["from"] in adj and e["to"] in adj:
            adj[e["from"]].append(e["to"])
    index: dict[str, int] = {}; low: dict[str, int] = {}; on: set[str] = set()
    stack: list[str] = []; sccs: list[list[str]] = []; counter = [0]
    for start in sorted(node_ids):
        if start in index:
            continue
        work: list[tuple[str, int]] = [(start, 0)]
        while work:
            v, pi = work[-1]
            if pi == 0:
                index[v] = low[v] = counter[0]; counter[0] += 1
                stack.append(v); on.add(v)
            recurse = False
            for w in adj[v][pi:]:
                work[-1] = (v, pi + 1); pi += 1
                if w not in index:
                    work.append((w, 0)); recurse = True; break
                if w in on:
                    low[v] = min(low[v], index[w])
            if recurse:
                continue
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop(); on.discard(w); comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1:
                    sccs.append(sorted(comp))
            work.pop()
            if work:
                u = work[-1][0]
                low[u] = min(low[u], low[v])
    return sorted(sccs)


def _dynamic_dep_warnings(nodes: list[Node], root: Path) -> list[dict[str, str]]:
    """Heuristic pass over claimed .py files for edges the extractor can't see."""
    from . import claims as claims_mod
    warnings: list[dict[str, str]] = []
    for node in sorted(nodes, key=lambda n: n.id):
        for claim in claims_mod.expand_claims(root, node.claims):
            file = root / claim
            table = (_DYNAMIC_DEP_PATTERNS if file.suffix == ".py"
                     else _DYNAMIC_DEP_PATTERNS_JS if file.suffix in _JS_EXTS
                     else None)
            if table is None or not file.exists():
                continue
            try:
                text = file.read_text(encoding="utf-8", errors="replace")
            except OSError:                             # pragma: no cover - defensive
                continue
            for name, pattern in table:
                if pattern.search(text):
                    warnings.append({"node": node.id, "file": _norm(claim),
                                     "pattern": name})
    return warnings


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
        "claimedFileCount": None,  # filled in extract() — needs root
        "sideEffects": raw.get("contract", {}).get("sideEffects"),
        "spanName": raw.get("observability", {}).get("spanName"),
        "approvalRequired": bool(raw.get("approval", {}).get("required", False)),
    }


def _composite_of(node: Node | None, root: Path) -> str | None:
    """Current composite version of a node (for span-staleness), or None."""
    if node is None:
        return None
    try:
        return compute_version(node, root).get("composite")
    except (OSError, ValueError, KeyError, TypeError):  # v6 5.6 — a half-written
        return None                                     # tree; other bugs raise


def extract(root: Path, *, spans: dict[tuple[str, str], Any] | None = None) -> ExtractResult:
    """Build the graph + coverage for a project and reconcile against reality.

    `spans` (from `ent.spans.observe*`) verifies declared edges from recorded
    runtime observations, on top of static import analysis (V1).
    """
    root = Path(root).resolve()
    nodes = _load_nodes(root)

    owner, doubles = _ownership(nodes, root)
    edges, edge_errors = _build_edges(nodes, owner, root, observed=spans)
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

    # Declared edges no runtime span has confirmed (V1) — the honest gap between
    # "declared" and "verified". Config edges are never runtime calls, so exclude
    # them: they can't be span-verified and would be permanent noise here.
    unverified = [
        {"from": e["from"], "to": e["to"], "kinds": e["kinds"]}
        for e in edges
        if e["declared"] and not e["verified"] and e["kinds"] != ["config"]
    ]

    from . import claims as claims_mod
    summaries = []
    for n in sorted(nodes, key=lambda n: n.id):
        s = _node_summary(n)
        # true mass (v7): how many files this unit actually owns once globs
        # expand — the Code City lens sizes territory by this, not by vibes.
        s["claimedFileCount"] = len(claims_mod.expand_claims(root, n.claims))
        summaries.append(s)

    graph = {
        "apiVersion": "entiendo/v1",
        "nodes": summaries,
        "edges": edges,
        "doubleClaimed": doubles,
        "proposedEntrypoints": proposals,
        "unverifiedDeclaredEdges": unverified,
        # v6 3.5 — constructs static analysis is blind to (dynamic imports,
        # string dispatch, out-of-process calls). Warnings, never failures.
        "possibleUndeclaredDynamicDep": _dynamic_dep_warnings(nodes, root),
        # v7 — circular dependency groups (SCCs > 1). A knot the layered
        # layout can't untangle deserves a name, not silence.
        "dependencyCycles": _dependency_cycles({n.id for n in nodes}, edges),
        # research round 2 — each language adapter's capability manifest: the
        # constructs it produces no edges for. The closed-world guarantee is
        # only as complete as each adapter's resolver; the holes are declared
        # in the artifact itself, machine-readably, never hidden.
        "adapters": [
            {
                "language": ex.name,
                "extensions": sorted(ex.extensions),
                "grade": ex.capabilities().grade,
                "evidenceTag": ex.capabilities().evidenceTag,
                "cannotResolve": list(ex.capabilities().cannotResolve),
            }
            for ex in languages.registered()
        ],
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

"""Retrofit — AI/heuristic-proposed manifests for an existing repo (SPEC §12 v2).

Greenfield registers a manifest at birth; retrofit is the harder problem of
*inferring* boundaries nobody declared — and it will guess wrong often. So this
is a **semi-automated migration, not a scan**: `ent retrofit` proposes a manifest
per inferred node into a staging area, each with a confidence and notes, and a
human accepts them node by node (`ent retrofit accept <id>`).

Inference (deliberately simple and legible, so a human can correct it):
  - group source files by their immediate directory (root-level files stand alone)
  - id = '<app>.<dotted dir path>' (app = the target's basename) so ids are stable
  - nodeKind from the file extensions (compute / config / state)
  - dependencies from static import analysis between candidate groups (same engine
    the extractor uses to verify edges)
  - entrypoint proposed when a group has a single obvious public function or an
    existing @ent.node() callable

Nothing is written into the real tree until a human accepts a proposal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .evals.entrypoint import scan_decorated
from .extractor import _imports, _resolve_import
from .manifest import _SKIP_DIRS

_CODE_EXT = {".py", ".ts", ".tsx", ".js", ".go", ".rs", ".java", ".rb"}
_CONFIG_EXT = {".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".env"}
_STATE_EXT = {".sql"}
_SOURCE_EXT = _CODE_EXT | _CONFIG_EXT | _STATE_EXT

PROPOSALS_DIR = "entiendo/proposals"


@dataclass
class Proposal:
    node_id: str
    manifest: dict[str, Any]
    target_dir: str          # where the entiendo.node.yaml would live (repo-relative)
    confidence: str          # high | medium | low
    notes: list[str] = field(default_factory=list)


def _sanitize(part: str) -> str:
    part = re.sub(r"[^a-z0-9_]", "_", part.lower())
    return re.sub(r"_+", "_", part).strip("_") or "mod"


def _candidate_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in _SOURCE_EXT:
            continue
        parts = path.relative_to(root).parts
        if any(p in _SKIP_DIRS for p in parts) or parts[0] == "entiendo":
            continue
        if any(p.startswith(".") for p in parts) or path.name == "entiendo.node.yaml":
            continue
        out.append(path)
    return sorted(out)


def _group_key(rel: Path) -> tuple[str, ...]:
    """Group by immediate directory; root-level files stand alone by stem."""
    parent = rel.parent
    if parent == Path("."):
        return (rel.stem,)
    return parent.parts


def _infer_kind(files: list[Path]) -> tuple[str, str]:
    exts = {f.suffix for f in files}
    if exts & _CODE_EXT:
        return "compute", "high"
    if exts <= _CONFIG_EXT:
        return "config", "high"
    if exts <= _STATE_EXT:
        return "state", "high"
    return "compute", "low"


def _propose_entrypoint(node_id: str, files: list[Path], root: Path) -> tuple[str | None, str | None]:
    """Return (entrypoint, note). Prefer an @ent.node() callable, else a lone function."""
    import ast

    for f in files:
        if f.suffix != ".py":
            continue
        rel = f.relative_to(root).as_posix()
        decorated = scan_decorated(f)
        for func, nid in decorated.items():
            if nid == node_id:
                return f"{rel}::{func}", None
        try:
            tree = ast.parse(f.read_text())
        except (SyntaxError, UnicodeDecodeError, ValueError):
            continue
        funcs = [n.name for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")]
        if len(funcs) == 1:
            return f"{rel}::{funcs[0]}", None
    return None, "no single obvious entrypoint — set contract.entrypoint by hand"


def propose(root: Path) -> list[Proposal]:
    """Infer candidate nodes and build proposed manifests. Writes nothing."""
    root = Path(root).resolve()
    app = _sanitize(root.name)
    files = _candidate_files(root)

    # group files → candidate node
    groups: dict[tuple[str, ...], list[Path]] = {}
    for f in files:
        groups.setdefault(_group_key(f.relative_to(root)), []).append(f)

    def gid(key: tuple[str, ...]) -> str:
        return ".".join([app] + [_sanitize(k) for k in key])

    owner: dict[str, str] = {}   # repo-relative file → node id
    for key, gfiles in groups.items():
        for f in gfiles:
            owner[f.relative_to(root).as_posix()] = gid(key)

    proposals: list[Proposal] = []
    for key, gfiles in sorted(groups.items()):
        node_id = gid(key)
        kind, kind_conf = _infer_kind(gfiles)
        claims = [f.relative_to(root).as_posix() for f in gfiles]
        target_dir = (gfiles[0].parent.relative_to(root)).as_posix()

        # dependencies via static imports between groups
        calls: set[str] = set()
        for f in gfiles:
            if f.suffix != ".py":
                continue
            for module, level in _imports(f):
                tgt = _resolve_import(module, level, f, root)
                if tgt is None:
                    continue
                dep = owner.get(tgt.resolve().relative_to(root).as_posix())
                if dep and dep != node_id:
                    calls.add(dep)

        notes: list[str] = []
        entrypoint = None
        if kind == "compute":
            entrypoint, ep_note = _propose_entrypoint(node_id, gfiles, root)
            if ep_note:
                notes.append(ep_note)

        contract: dict[str, Any] = {"invariants": [], "sideEffects": "none"}
        if entrypoint:
            contract = {"entrypoint": entrypoint, **contract}

        confidence = "high" if (kind_conf == "high" and (entrypoint or kind != "compute")) else \
                     "low" if kind_conf == "low" else "medium"
        notes.append("owner, contract, and evals are stubs — review before accepting")
        # A unit is only valid if it can be evaluated on given data (the law).
        # Retrofit cannot author that data, so every proposal is boundary-uncertain
        # until a human supplies a fixture -> expected verdict (see `ent new`).
        notes.append("boundary-uncertain: no candidate fixture -> expected verdict yet; "
                     "supply one before accepting (the law)")

        task = f"TODO: state in one sentence what {node_id} is for (retrofit inferred this boundary)"
        manifest = {
            "apiVersion": "entiendo/v1", "kind": "Node",
            "id": node_id, "name": key[-1], "task": task, "nodeKind": kind, "group": app,
            "owner": "TODO", "status": "experimental",
            "claims": claims,
            "contract": contract,
            "dependencies": {"calls": sorted(calls), "reads": [], "writes": [], "config": []},
            "evals": {"tier0": [{"type": "invariant_check"}]},
            "observability": {"spanName": node_id},
            "approval": {"required": False},
        }
        proposals.append(Proposal(node_id, manifest, target_dir, confidence, notes))

    return proposals


def coverage(root: Path, proposals: list[Proposal]) -> dict[str, Any]:
    total = len(_candidate_files(Path(root).resolve()))
    claimed = sum(len(p.manifest["claims"]) for p in proposals)
    return {"total": total, "claimed": claimed,
            "coverage": round(claimed / total, 4) if total else 1.0,
            "nodes": len(proposals)}


def write_proposals(root: Path, proposals: list[Proposal]) -> Path:
    """Write proposals to entiendo/proposals/<id>.node.yaml. Returns the dir."""
    import yaml

    root = Path(root).resolve()
    out = root / PROPOSALS_DIR
    out.mkdir(parents=True, exist_ok=True)
    for p in proposals:
        header = (f"# PROPOSED by `ent retrofit` — confidence: {p.confidence}\n"
                  f"# target: {p.target_dir}/entiendo.node.yaml\n"
                  + "".join(f"# note: {n}\n" for n in p.notes))
        (out / f"{p.node_id}.node.yaml").write_text(header + yaml.safe_dump(p.manifest, sort_keys=False))
    return out


def accept(root: Path, node_id: str) -> Path | None:
    """Move a proposal into place as a real entiendo.node.yaml. Returns the path."""
    import yaml

    root = Path(root).resolve()
    proposal_file = root / PROPOSALS_DIR / f"{node_id}.node.yaml"
    if not proposal_file.exists():
        return None
    manifest = yaml.safe_load(proposal_file.read_text())
    # target dir: recompute from claims (first claim's parent)
    claims = manifest.get("claims", [])
    target_dir = root / (Path(claims[0]).parent if claims else Path("."))
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / "entiendo.node.yaml"
    dest.write_text(yaml.safe_dump(manifest, sort_keys=False))
    proposal_file.unlink()
    return dest

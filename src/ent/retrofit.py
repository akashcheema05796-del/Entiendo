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
    existing @ent.node() callable — and only when it actually IMPORTS here:
    every candidate is probed in a bounded child first (astrobee shipped 5
    proposals whose entrypoints import ROS packages that can never resolve
    outside a ROS install — each one a fake ERROR waiting at eval time)

Nothing is written into the real tree until a human accepts a proposal.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .evals.entrypoint import scan_decorated
from . import languages
from .manifest import iter_project_files

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
    return sorted(p for p in iter_project_files(root)
                  if p.is_file() and p.suffix in _SOURCE_EXT)


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


def _entrypoint_candidates(node_id: str, files: list[Path], root: Path) -> list[str]:
    """Ordered candidate entrypoints: @ent.node() matches first, then every
    file with a single obvious public function (the original heuristic, kept
    as a ranking instead of a single blind pick)."""
    import ast

    decorated_specs: list[str] = []
    lone_specs: list[str] = []
    for f in files:
        if f.suffix != ".py":
            continue
        rel = f.relative_to(root).as_posix()
        for func, nid in scan_decorated(f).items():
            if nid == node_id:
                decorated_specs.append(f"{rel}::{func}")
        try:
            tree = ast.parse(f.read_text())
        except (SyntaxError, UnicodeDecodeError, ValueError, OSError):
            continue
        funcs = [n.name for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")]
        if len(funcs) == 1:
            lone_specs.append(f"{rel}::{funcs[0]}")
    return decorated_specs + [s for s in lone_specs if s not in decorated_specs]


# How many candidates to probe per group before giving up — probing spawns a
# child process each, and a group whose first three candidates all fail to
# import is overwhelmingly one whose remaining files need the same missing
# runtime (astrobee: rosbag across a whole scripts/ dir).
_PROBE_MAX_CANDIDATES = 3
_PROBE_TIMEOUT_S = 10.0

# The child mirrors the EVAL loader exactly (same package-context resolution,
# same sys.path discipline) — a probe that imports differently from the judge
# would certify entrypoints the judge still can't load.
_PROBE_CODE = """\
import json, sys
from pathlib import Path
from ent.evals.entrypoint import _import_file
root = Path(sys.argv[1]); spec = sys.argv[2]
rel, _, name = spec.partition("::")
try:
    mod = _import_file(root / rel, "retrofit-probe", root)
    fn = getattr(mod, name, None)
    ok = callable(fn)
    err = None if ok else f"'{name}' is not a callable in {rel}"
except BaseException as exc:      # SystemExit at import is a real-world case
    ok, err = False, f"{type(exc).__name__}: {exc}"[:300]
print("ENT-PROBE:" + json.dumps({"ok": ok, "error": err}))
"""


def probe_entrypoint(root: Path, spec: str, timeout_s: float = _PROBE_TIMEOUT_S) -> str | None:
    """None if `spec` imports to a callable in THIS environment, else why not.

    Runs in a bounded child (rlimits + wall clock), never in-process: a
    proposed entrypoint is arbitrary unvetted code — importing it may
    sys.exit, block forever, or exhaust memory (the same lesson the accept
    flow learned from node.js's configure script).
    """
    import json
    import subprocess
    import sys

    from .sandbox import _apply_rlimits

    kwargs: dict[str, Any] = {}
    if os.name == "posix":
        kwargs["preexec_fn"] = _apply_rlimits
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _PROBE_CODE, str(Path(root).resolve()), spec],
            capture_output=True, text=True, cwd=str(root),
            timeout=timeout_s, **kwargs)
    except subprocess.TimeoutExpired:
        return f"import timed out after {timeout_s:.0f}s"
    except OSError as exc:
        return f"probe could not spawn: {exc}"
    # A hostile import may spray stdout before the marker — scan for ours.
    for line in reversed((proc.stdout or "").splitlines()):
        if line.startswith("ENT-PROBE:"):
            try:
                data = json.loads(line[len("ENT-PROBE:"):])
            except ValueError:
                break
            return None if data.get("ok") else (data.get("error") or "not importable")
    return f"import died before completing (exit {proc.returncode})"


def propose(root: Path, probe: bool = True) -> list[Proposal]:
    """Infer candidate nodes and build proposed manifests. Writes nothing.

    `probe=False` skips the import probe on candidate entrypoints (faster,
    but restores the old blind-guess behaviour — proposals may then carry
    entrypoints that can never import and will read ERROR at eval time).
    """
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

        # dependencies via static imports between groups (per-language seam)
        calls: set[str] = set()
        for f in gfiles:
            extractor = languages.for_file(f)
            if extractor is None:
                continue
            for imp in extractor.resolved_imports(f, root):
                dep = owner.get(imp.target.resolve().relative_to(root.resolve()).as_posix())
                if dep and dep != node_id:
                    calls.add(dep)

        notes: list[str] = []
        entrypoint = None
        if kind == "compute":
            cands = _entrypoint_candidates(node_id, gfiles, root)
            if not cands:
                notes.append("no single obvious entrypoint — set contract.entrypoint by hand")
            elif not probe:
                entrypoint = cands[0]
            else:
                last_err: str | None = None
                for spec in cands[:_PROBE_MAX_CANDIDATES]:
                    err = probe_entrypoint(root, spec)
                    if err is None:
                        entrypoint = spec
                        break
                    last_err = err
                if entrypoint is None:
                    probed = min(len(cands), _PROBE_MAX_CANDIDATES)
                    notes.append(
                        f"no importable entrypoint in this environment — probed "
                        f"{probed} candidate(s); last failure: {last_err}")

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


def accept(root: Path, node_id: str) -> tuple[Path, list[tuple[str, str]]] | None:
    """Move a proposal into place as a real entiendo.node.yaml.

    Returns (path, held_back_edges) or None if no such proposal.

    A proposal's inferred dependencies may point at SIBLING proposals that
    are not accepted yet — promoting those edges verbatim leaves the partial
    project broken (`declares dependency on unknown node`), which betrays
    the guarantee that the first manifest yields a working project. Edges
    to units that don't exist yet are HELD BACK and reported; when the
    sibling is later accepted, the reconciler's undeclared-dependency drift
    will name the missing edge — the system reminds you, mechanically.
    """
    import yaml

    from .manifest import discover, load

    root = Path(root).resolve()
    proposal_file = root / PROPOSALS_DIR / f"{node_id}.node.yaml"
    if not proposal_file.exists():
        return None
    manifest = yaml.safe_load(proposal_file.read_text())

    accepted_ids = {load(p).get("id") for p in discover(root)} | {node_id}
    held: list[tuple[str, str]] = []
    deps = manifest.get("dependencies") or {}
    for kind, targets in list(deps.items()):
        if not isinstance(targets, list):
            continue
        kept = [t for t in targets if t in accepted_ids]
        held += [(kind, t) for t in targets if t not in accepted_ids]
        deps[kind] = kept

    # target dir: recompute from claims (first claim's parent)
    claims = manifest.get("claims", [])
    target_dir = root / (Path(claims[0]).parent if claims else Path("."))
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / "entiendo.node.yaml"
    dest.write_text(yaml.safe_dump(manifest, sort_keys=False))
    proposal_file.unlink()
    return dest, held

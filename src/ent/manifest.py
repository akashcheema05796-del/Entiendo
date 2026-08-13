"""L0 — Manifest model. The core primitive of Entiendo.

A node is declared by exactly one `entiendo.node.yaml`, colocated with the
module it describes (SPEC.md §1.3). This module discovers, loads, and offers a
thin typed view over those files. The authoritative *contract* is
schemas/node.schema.json — this module never re-implements validation, it defers
to it (see schema.py + validation.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

# Every node is declared by a file with this exact name (SPEC.md §1.3).
MANIFEST_FILENAME = "entiendo.node.yaml"

# The manifest apiVersion this scaffold speaks.
API_VERSION = "entiendo/v1"

# Node kinds and how each is drawn on the map (SPEC.md §1.1).
NODE_KINDS = ("compute", "state", "schema", "config", "external", "pipeline")

# Side-effect classes, ordered from safest to most dangerous. Drives blast radius.
SIDE_EFFECTS = ("none", "writes", "external", "irreversible")

# Lifecycle states.
STATUSES = ("active", "deprecated", "experimental")

# Directories that never contain project manifests — skip them during discovery.
_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache",
             ".pytest_cache", "dist", "build"}


def schema_path() -> Path:
    """Absolute path to the bundled node JSON-Schema.

    Installed wheels carry the schema INSIDE the package (ent/schemas/ — see
    the pyproject force-include); a repo checkout finds the same file at the
    repo root. Package copy wins so `pip install entiendo` works outside a
    checkout; the repo copy stays the single source of truth for edits.
    """
    packaged = Path(__file__).resolve().parent / "schemas" / "node.schema.json"
    if packaged.exists():
        return packaged
    # src/ent/manifest.py → repo root is two parents up from src/ent.
    return Path(__file__).resolve().parents[2] / "schemas" / "node.schema.json"


def is_foreign_root(cur: Path, root: Path) -> bool:
    """A directory strictly below `root` that is its own project: it carries
    its own `entiendo/` control plane or its own `.git`. Its manifests' claims
    resolve against *that* root, so every walk (discovery, coverage, retrofit)
    must stop at it — sweeping it into this project misroots every claim (the
    Entiendo repo itself hit this: a root-level walk swallowed the examples)."""
    return cur != root and ((cur / "entiendo").is_dir() or (cur / ".git").exists())


def discover(root: Path) -> list[Path]:
    """Find every `entiendo.node.yaml` under `root`, sorted for stable output.

    Prunes vendored / generated directories and nested project roots.
    """
    import os

    root = Path(root)
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        cur = Path(dirpath)
        if is_foreign_root(cur, root):
            dirnames[:] = []            # a different project's tree — don't descend
            continue
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        if MANIFEST_FILENAME in filenames:
            found.append(cur / MANIFEST_FILENAME)
    return sorted(found)


def iter_project_files(root: Path) -> "Iterator[Path]":
    """Every file that belongs to THIS project, deterministically ordered.

    One boundary rule for all walks: prunes vendored dirs (`_SKIP_DIRS`),
    dot-directories and dotfiles, the project's own `entiendo/` artifact tree,
    the manifests themselves, and nested project roots (`is_foreign_root`).
    Callers layer their own filters (suffix, etc.) on top.
    """
    import os

    root = Path(root)
    root_real = os.path.realpath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        cur = Path(dirpath)
        if is_foreign_root(cur, root):
            dirnames[:] = []
            continue
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in _SKIP_DIRS and not d.startswith(".")
            and not (cur == root and d == "entiendo")
        )
        for name in sorted(filenames):
            if name == MANIFEST_FILENAME or name.startswith("."):
                continue
            f = cur / name
            # Real repos contain hostile entries (found the hard way, on 100
            # of them): symlinks escaping the root (jekyll ships one pointing
            # at /etc/passwd) and names the OS cannot even stat (ENAMETOOLONG
            # in trpc). Neither is this project's file: symlink escapes are
            # never followed, unstat-able entries are skipped — and neither
            # is ever fatal to the walk.
            try:
                if f.is_symlink():
                    real = os.path.realpath(f)
                    if os.path.commonpath([real, root_real]) != root_real:
                        continue
                if not f.is_file():
                    continue
            except (OSError, ValueError):
                continue
            yield f


def load(path: Path) -> dict[str, Any]:
    """Parse a manifest file into a plain dict.

    Raises:
        ModuleNotFoundError: if `pyyaml` is not installed.
        yaml.YAMLError: if the file is not valid YAML.
        ValueError: if the document is not a mapping.
    """
    import yaml  # local import: keeps the dependency lazy

    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: manifest must be a YAML mapping, got {type(data).__name__}")
    return data


def find_node(root: Path, node_id: str) -> "Node | None":
    """Load the node with the given id from a project, or None if absent."""
    for path in discover(Path(root)):
        data = load(path)
        if data.get("id") == node_id:
            return Node.from_manifest(data, path)
    return None


@dataclass(frozen=True)
class Node:
    """A thin typed view over a parsed manifest.

    Only surfaces the fields the L0 tooling needs today; the raw dict is kept on
    `.raw` so later phases can reach anything without a model change.
    """

    id: str
    node_kind: str
    path: Path
    claims: tuple[str, ...]
    raw: dict[str, Any]

    @classmethod
    def from_manifest(cls, data: dict[str, Any], path: Path) -> "Node":
        return cls(
            id=data.get("id", ""),
            node_kind=data.get("nodeKind", ""),
            path=Path(path),
            claims=tuple(data.get("claims", []) or []),
            raw=data,
        )

"""L0 — Manifest model. The core primitive of Entiendo.

STUB. Phase 1 turns this into a typed loader/model for entiendo.node.yaml. For
now it documents the shape and offers the constants the rest of the scaffold
agrees on. The authoritative contract is schemas/node.schema.json — this module
must never drift from it (that reconciliation is itself an L0 acceptance test).
"""

from __future__ import annotations

from pathlib import Path

# Every node is declared by a file with this exact name, colocated with the
# module it describes (SPEC.md §1.3).
MANIFEST_FILENAME = "entiendo.node.yaml"

# The manifest apiVersion this scaffold speaks.
API_VERSION = "entiendo/v1"

# Node kinds and how each is drawn on the map (SPEC.md §1.1).
NODE_KINDS = ("compute", "state", "schema", "config", "external", "pipeline")

# Side-effect classes, ordered from safest to most dangerous. Drives blast radius.
SIDE_EFFECTS = ("none", "writes", "external", "irreversible")

# Lifecycle states.
STATUSES = ("active", "deprecated", "experimental")


def schema_path() -> Path:
    """Absolute path to the bundled node JSON-Schema.

    Resolved relative to the repo root so tests and the (future) validator agree
    on a single source of truth.
    """
    # src/ent/manifest.py → repo root is two parents up from src/ent.
    return Path(__file__).resolve().parents[2] / "schemas" / "node.schema.json"


# Phase 1 will add:
#   @dataclass class Node: ...           # typed view over the parsed yaml
#   def load(path: Path) -> Node: ...    # parse + normalise
#   def discover(root: Path) -> list[Path]: ...  # find every manifest

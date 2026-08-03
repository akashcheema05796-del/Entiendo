"""Baselines + blessing storage (Phase 7 §8, §10). Append-only, boring formats.

    entiendo/baselines/<node-id>.json          active baseline
    entiendo/baselines/<node-id>.pending.json  proposed baseline (ent baseline accept)
    entiendo/baselines/<node-id>.bless.json     dataset signature

`humanBlessed` has teeth: blessing is a signature over the dataset *content*
(sha256), not the filename. At tier1 time the runner rehashes the dataset; if it
differs, the blessing is void — the golden rows changed since a human looked at
them — and the run is advisory-only. That is the single defence against the AI
grading its own homework by editing its own golden rows.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

BASELINES_DIR = "entiendo/baselines"


def _dir(root: Path) -> Path:
    d = Path(root) / BASELINES_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def baseline_path(root: Path, node_id: str) -> Path:
    return _dir(root) / f"{node_id}.json"


def pending_path(root: Path, node_id: str) -> Path:
    return _dir(root) / f"{node_id}.pending.json"


def bless_path(root: Path, node_id: str) -> Path:
    return _dir(root) / f"{node_id}.bless.json"


def dataset_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --- baselines ------------------------------------------------------------- #

def read_baseline(root: Path, node_id: str) -> dict[str, Any] | None:
    p = baseline_path(root, node_id)
    return json.loads(p.read_text()) if p.exists() else None


def write_baseline(root: Path, node_id: str, data: dict[str, Any]) -> Path:
    p = baseline_path(root, node_id)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return p


def write_pending(root: Path, node_id: str, data: dict[str, Any]) -> Path:
    p = pending_path(root, node_id)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return p


def read_pending(root: Path, node_id: str) -> dict[str, Any] | None:
    p = pending_path(root, node_id)
    return json.loads(p.read_text()) if p.exists() else None


def accept_pending(root: Path, node_id: str) -> dict[str, Any] | None:
    """Promote a pending baseline to active. Returns the promoted data, or None."""
    pending = read_pending(root, node_id)
    if pending is None:
        return None
    write_baseline(root, node_id, pending)
    pending_path(root, node_id).unlink()
    return pending


# --- blessing -------------------------------------------------------------- #

def write_bless(
    root: Path, node_id: str, *, dataset_rel: str, sha: str, rows: int,
    blessed_by: str, blessed_at: str,
) -> Path:
    # A blessing must carry a real identity (V3) — "unknown" is not writable.
    from .identity import is_valid_blesser
    if not is_valid_blesser(blessed_by):
        raise ValueError(
            f"refusing to write a blessing with no real blesser (got {blessed_by!r}) — "
            "resolve an identity via --as / entiendo/config.toml / git user.email")
    record = {
        "dataset": dataset_rel,
        "datasetSha256": sha,
        "rows": rows,
        "blessedBy": blessed_by,
        "blessedAt": blessed_at,
    }
    p = bless_path(root, node_id)
    p.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return p


def read_bless(root: Path, node_id: str) -> dict[str, Any] | None:
    p = bless_path(root, node_id)
    return json.loads(p.read_text()) if p.exists() else None


def blessing_valid(root: Path, node_id: str, dataset_path: Path) -> bool:
    """True iff there is a blessing whose signature matches the current dataset."""
    record = read_bless(root, node_id)
    if record is None or not Path(dataset_path).exists():
        return False
    return record.get("datasetSha256") == dataset_sha256(dataset_path)

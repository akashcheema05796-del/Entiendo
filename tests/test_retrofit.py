"""Retrofit — proposing manifests for an unmanaged repo (SPEC §12 v2)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import retrofit  # noqa: E402
from ent.validation import validate_root  # noqa: E402
from ent.extractor import extract  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY = REPO_ROOT / "examples" / "legacy"


def test_proposes_a_node_per_module() -> None:
    proposals = retrofit.propose(LEGACY)
    ids = {p.node_id for p in proposals}
    assert ids == {"legacy.orders", "legacy.catalog", "legacy.ledger", "legacy.settings"}


def test_infers_dependencies_from_imports() -> None:
    proposals = {p.node_id: p for p in retrofit.propose(LEGACY)}
    orders = proposals["legacy.orders"]
    assert set(orders.manifest["dependencies"]["calls"]) == {"legacy.catalog", "legacy.ledger"}


def test_infers_kind_and_entrypoint() -> None:
    proposals = {p.node_id: p for p in retrofit.propose(LEGACY)}
    assert proposals["legacy.settings"].manifest["nodeKind"] == "config"
    orders = proposals["legacy.orders"].manifest
    assert orders["nodeKind"] == "compute"
    # a single public function → a proposed entrypoint
    assert orders["contract"]["entrypoint"] == "orders/service.py::place_order"


def test_coverage_is_full() -> None:
    proposals = retrofit.propose(LEGACY)
    cov = retrofit.coverage(LEGACY, proposals)
    assert cov["coverage"] == 1.0
    assert cov["nodes"] == 4


def _copy_legacy(tmp_path: Path) -> Path:
    import shutil

    dst = tmp_path / "legacy"
    shutil.copytree(LEGACY, dst, ignore=shutil.ignore_patterns(".gitignore", "entiendo", "README.md"))
    return dst


def test_accept_writes_valid_reconciling_manifests(tmp_path: Path) -> None:
    root = _copy_legacy(tmp_path)
    proposals = retrofit.propose(root)
    retrofit.write_proposals(root, proposals)
    for p in proposals:
        assert retrofit.accept(root, p.node_id) is not None

    # The accepted manifests validate...
    report = validate_root(root)
    assert report.ok, [r.errors for r in report.results if not r.ok] + report.cross_errors
    # ...and the inferred graph reconciles (deps were derived from real imports).
    result = extract(root)
    assert result.ok, result.errors


def test_accept_missing_proposal_returns_none(tmp_path: Path) -> None:
    root = _copy_legacy(tmp_path)
    assert retrofit.accept(root, "nope.node") is None

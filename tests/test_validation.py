"""L0 validation tests — the real logic (Phase 1).

Covers the acceptance criterion (SPEC.md §8, Phase 1): well-formed manifests
validate; a malformed one fails with a useful, specific error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("jsonschema")
pytest.importorskip("yaml")

from ent.validation import validate_paths, validate_root  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"

WELL_FORMED = """\
apiVersion: entiendo/v1
kind: Node
id: demo.node
name: Demo
nodeKind: compute
owner: me
claims: [source.py]
contract:
  invariants: []
  sideEffects: none
evals:
  tier0:
    - type: schema_validation
"""


def _write(tmp_path: Path, body: str) -> Path:
    # Claims are resolved relative to the project root (tmp_path here), matching
    # how the greenfield example and `ent validate --root` behave.
    (tmp_path / "source.py").write_text("# claimed\n")
    mod = tmp_path / "mod"
    mod.mkdir()
    manifest = mod / "entiendo.node.yaml"
    manifest.write_text(body)
    return manifest


def test_greenfield_example_validates() -> None:
    report = validate_root(GREENFIELD)
    assert report.ok, [r.errors for r in report.results if not r.ok] + report.cross_errors


def test_well_formed_manifest_validates(tmp_path: Path) -> None:
    manifest = _write(tmp_path, WELL_FORMED)
    report = validate_paths([manifest], root=tmp_path)
    assert report.ok, report.results[0].errors


def test_bad_node_kind_fails_with_useful_error(tmp_path: Path) -> None:
    manifest = _write(tmp_path, WELL_FORMED.replace("nodeKind: compute", "nodeKind: wizard"))
    report = validate_paths([manifest], root=tmp_path)
    assert not report.ok
    assert any("nodeKind" in e for e in report.results[0].errors)


def test_missing_required_field_fails(tmp_path: Path) -> None:
    body = "\n".join(l for l in WELL_FORMED.splitlines() if not l.startswith("owner:"))
    manifest = _write(tmp_path, body)
    report = validate_paths([manifest], root=tmp_path)
    assert not report.ok
    assert any("owner" in e for e in report.results[0].errors)


def test_claim_on_missing_file_fails(tmp_path: Path) -> None:
    manifest = _write(tmp_path, WELL_FORMED.replace("claims: [source.py]", "claims: [ghost.py]"))
    report = validate_paths([manifest], root=tmp_path)
    assert not report.ok
    assert any("ghost.py" in e and "does not exist" in e for e in report.results[0].errors)


def test_unblessed_golden_fails(tmp_path: Path) -> None:
    body = WELL_FORMED + """\
  tier1:
    - type: golden
      dataset: evals/x.jsonl
      humanBlessed: false
"""
    manifest = _write(tmp_path, body)
    report = validate_paths([manifest], root=tmp_path)
    assert not report.ok
    assert any("humanBlessed" in e for e in report.results[0].errors)


def test_duplicate_ids_reported_cross_file(tmp_path: Path) -> None:
    (tmp_path / "source.py").write_text("# claimed\n")
    a = tmp_path / "a"
    b = tmp_path / "b"
    for d in (a, b):
        d.mkdir()
        (d / "entiendo.node.yaml").write_text(WELL_FORMED)
    report = validate_paths([a / "entiendo.node.yaml", b / "entiendo.node.yaml"], root=tmp_path)
    assert not report.ok
    assert any("duplicate node id" in e for e in report.cross_errors)


def test_empty_root_reports_no_manifests(tmp_path: Path) -> None:
    report = validate_root(tmp_path)
    assert not report.ok
    assert any("no entiendo.node.yaml" in e for e in report.cross_errors)

"""Scaffold-coherence tests.

These do NOT test tool logic (there is none yet). They prove the scaffold is
internally consistent so later phases build on solid ground:

  - the bundled node schema is itself a valid JSON-Schema
  - every example manifest conforms to that schema
  - the example node ids are unique and the referenced eval fixtures exist

If pyyaml / jsonschema aren't installed, the schema-driven tests skip rather
than fail — the scaffold must stay trivially recoverable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schemas" / "node.schema.json"
GREENFIELD = REPO_ROOT / "examples" / "greenfield"


def _manifest_paths() -> list[Path]:
    return sorted(GREENFIELD.rglob("entiendo.node.yaml"))


def test_schema_is_readable_json() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    assert schema["title"] == "Entiendo Node Manifest"
    assert schema["properties"]["apiVersion"]["const"] == "entiendo/v1"


def test_example_project_has_five_nodes() -> None:
    # The MVP slice is five nodes (SPEC.md §9).
    assert len(_manifest_paths()) == 5


def test_schema_is_a_valid_jsonschema() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text())
    # Raises if the schema itself is malformed.
    jsonschema.Draft202012Validator.check_schema(schema)


def test_example_manifests_conform() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    yaml = pytest.importorskip("yaml")
    schema = json.loads(SCHEMA_PATH.read_text())
    validator = jsonschema.Draft202012Validator(schema)

    seen_ids: set[str] = set()
    for path in _manifest_paths():
        manifest = yaml.safe_load(path.read_text())
        errors = sorted(validator.iter_errors(manifest), key=lambda e: e.path)
        assert not errors, f"{path.relative_to(REPO_ROOT)}: {errors[0].message}"

        node_id = manifest["id"]
        assert node_id not in seen_ids, f"duplicate node id: {node_id}"
        seen_ids.add(node_id)


def test_referenced_eval_fixtures_exist() -> None:
    yaml = pytest.importorskip("yaml")
    for path in _manifest_paths():
        manifest = yaml.safe_load(path.read_text())
        for check in manifest.get("evals", {}).get("tier0", []):
            fixture = check.get("fixture")
            if fixture:
                assert (GREENFIELD / fixture).exists(), f"missing fixture: {fixture}"

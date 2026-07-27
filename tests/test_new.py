"""Phase F acceptance (PLAN_v3.md §F) — `ent new` cannot produce a unit without
a fixture pair; the unit it produces is green from birth (the law as a tool)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import cli  # noqa: E402
from ent.evals.runner import run_tier0  # noqa: E402
from ent.manifest import find_node  # noqa: E402
from ent.validation import validate_root  # noqa: E402


def _new(tmp_path: Path, *args: str) -> int:
    return cli.main(["new", *args, "--root", str(tmp_path)])


def test_refuses_without_task(tmp_path: Path) -> None:
    code = _new(tmp_path, "demo.thing", "--fixture", "{}", "--expect", "{}")
    assert code == 1
    assert not (tmp_path / "src").exists()          # nothing written


def test_refuses_without_fixture_pair(tmp_path: Path) -> None:
    code = _new(tmp_path, "demo.thing", "--task", "do a thing", "--fixture", '{"x":1}')
    assert code == 1                                  # missing --expect
    assert list(tmp_path.glob("**/entiendo.node.yaml")) == []


def test_refuses_bad_json(tmp_path: Path) -> None:
    code = _new(tmp_path, "demo.thing", "--task", "t", "--fixture", "{not json}", "--expect", "{}")
    assert code == 1


def test_refuses_undotted_id(tmp_path: Path) -> None:
    assert _new(tmp_path, "thing", "--task", "t", "--fixture", "{}", "--expect", "{}") == 1


def test_creates_green_unit_from_a_fixture_pair(tmp_path: Path) -> None:
    code = _new(tmp_path, "demo.newunit", "--task", "Echo x into y",
                "--fixture", '{"x": 1}', "--expect", '{"y": 1}')
    assert code == 0

    manifest = tmp_path / "src" / "newunit" / "entiendo.node.yaml"
    assert manifest.exists()
    assert (tmp_path / "src" / "newunit" / "newunit.py").exists()
    assert (tmp_path / "evals" / "demo.newunit" / "smoke.jsonl").exists()

    # the manifest carries the task and validates against the schema
    assert validate_root(tmp_path).ok
    node = find_node(tmp_path, "demo.newunit")
    assert node.raw["task"] == "Echo x into y"

    # green from birth — the placeholder returns the fixture's expected output
    assert run_tier0(node, tmp_path).verdict == "GREEN"


def test_refuses_to_overwrite(tmp_path: Path) -> None:
    ok = _new(tmp_path, "demo.thing", "--task", "t", "--fixture", "{}", "--expect", "{}")
    assert ok == 0
    again = _new(tmp_path, "demo.thing", "--task", "t2", "--fixture", "{}", "--expect", "{}")
    assert again == 1                                # refuses to clobber

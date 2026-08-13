"""Retrofit must never propose an entrypoint that cannot import (astrobee).

The astrobee retrofit shipped 5 units whose proposed entrypoints import ROS
packages (`rosbag`, `tf`, `localization_common`) that can never resolve
outside a ROS install — each one a guaranteed fake ERROR at eval time,
conflating "wrong environment" with "broken unit". Propose-time now probes
every candidate in a bounded child and only proposes ones that import HERE.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import retrofit  # noqa: E402


def _unit(tmp_path: Path, name: str, body: str) -> Path:
    root = tmp_path / "proj"
    (root / name).mkdir(parents=True, exist_ok=True)
    (root / name / "mod.py").write_text(body)
    return root


def _proposal(root: Path, needle: str, **kw):
    return next(p for p in retrofit.propose(root, **kw) if needle in p.node_id)


def test_unimportable_entrypoint_is_not_proposed(tmp_path: Path) -> None:
    root = _unit(tmp_path, "rosish",
                 "import module_that_does_not_exist_anywhere_xyz\n"
                 "def process(x):\n    return x\n")
    prop = _proposal(root, "rosish")
    assert "entrypoint" not in prop.manifest["contract"]
    note = next(n for n in prop.notes if "no importable entrypoint" in n)
    assert "module_that_does_not_exist_anywhere_xyz" in note


def test_importable_entrypoint_still_proposed(tmp_path: Path) -> None:
    root = _unit(tmp_path, "clean", "def double(x):\n    return x * 2\n")
    prop = _proposal(root, "clean")
    assert prop.manifest["contract"]["entrypoint"] == "clean/mod.py::double"


def test_probe_falls_through_to_the_importable_candidate(tmp_path: Path) -> None:
    """First candidate (alphabetically first file) needs a missing runtime;
    the sibling imports fine — the sibling must win, not silence."""
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "a_needs_ros.py").write_text(
        "import module_that_does_not_exist_anywhere_xyz\n"
        "def broken(x):\n    return x\n")
    (root / "pkg" / "b_pure.py").write_text("def works(x):\n    return x\n")
    prop = _proposal(root, "pkg")
    assert prop.manifest["contract"]["entrypoint"] == "pkg/b_pure.py::works"


def test_hostile_import_cannot_kill_propose(tmp_path: Path) -> None:
    """node.js flavour, now at propose time: a candidate that sys.exit()s at
    import must fail its probe in the child — never take retrofit down."""
    root = _unit(tmp_path, "hostile",
                 "import sys\nsys.exit(2)\n\ndef configure(x):\n    return x\n")
    prop = _proposal(root, "hostile")
    assert "entrypoint" not in prop.manifest["contract"]
    assert any("no importable entrypoint" in n for n in prop.notes)


def test_no_probe_restores_the_blind_guess(tmp_path: Path) -> None:
    root = _unit(tmp_path, "rosish",
                 "import module_that_does_not_exist_anywhere_xyz\n"
                 "def process(x):\n    return x\n")
    prop = _proposal(root, "rosish", probe=False)
    assert prop.manifest["contract"]["entrypoint"] == "rosish/mod.py::process"


def test_probed_entrypoint_matches_the_eval_loader_on_packages(tmp_path: Path) -> None:
    """A packaged module with a relative import only loads under its real
    dotted name — the probe must agree with the eval loader, or it certifies
    entrypoints the judge can't load."""
    root = tmp_path / "proj"
    pkg = root / "lib" / "core"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "helpers.py").write_text("VALUE = 3\n")
    (pkg / "api.py").write_text(
        "from .helpers import VALUE\n\ndef triple(x):\n    return x * VALUE\n")
    prop = _proposal(root, "core")
    assert prop.manifest["contract"]["entrypoint"] == "lib/core/api.py::triple"

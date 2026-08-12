"""Test-case extraction (hardening Phase 4) — every scenario the plan names.

Fixture suite: literal parametrize · computed parametrize (`[i*2 for i in
range(5)]`) · fixture-parametrized · class-level pytestmark · a
network-fixture case (flagged, never extracted) · a non-literal the AST
must skip and collection must catch. The safety contract under test: the
AST path never emits an evaluated value; nothing is silently wrong; the
coverage line always tells the truth.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("yaml")

from ent.extract import static_ast  # noqa: E402

FIXTURE_SUITE = """
    import pytest

    def double(x):
        return x * 2

    @pytest.mark.parametrize("n,expected", [(1, 2), (2, 4),
                                            pytest.param(3, 6, id="three")])
    def test_literal(n, expected):
        assert double(n) == expected

    @pytest.mark.parametrize("n", [i * 2 for i in range(5)])   # computed
    def test_computed(n):
        assert double(n) >= 0

    @pytest.fixture(params=["red", "blue"])
    def colour(request):
        return request.param

    def test_fixture_param(colour):
        assert isinstance(colour, str)

    class TestGrouped:
        pytestmark = pytest.mark.slow

        @pytest.mark.parametrize("s", ["a", "b"])
        def test_marked(self, s):
            assert s

    @pytest.fixture
    def server_conn():
        raise RuntimeError("network")

    def test_needs_network(server_conn):                       # needs_harness
        assert server_conn

    def test_plain_assert():
        assert double(21) == 42
"""


@pytest.fixture()
def suite(tmp_path: Path) -> Path:
    d = tmp_path / "legacy"
    d.mkdir()
    (d / "test_things.py").write_text(textwrap.dedent(FIXTURE_SUITE))
    return d


# --------------------------------------------------------------------------- #
# AST path: literal-only, never evaluates
# --------------------------------------------------------------------------- #

def test_ast_extracts_literals_and_never_the_computed_list(suite: Path) -> None:
    result = static_ast.extract_file(suite / "test_things.py")
    ids = {c["case_id"] for c in result["cases"]}
    assert "three" in ids                                  # pytest.param id kept
    assert any(c["inputs"] == {"n": 1} and c["expected"] == 2
               for c in result["cases"])
    # THE safety property: nothing from [i*2 for i in range(5)] appears
    assert not any("computed" in c["source_test"] for c in result["cases"])
    assert result["skipped_non_literal"] >= 1              # counted, not hidden


def test_ast_extracts_the_plain_assert(suite: Path) -> None:
    result = static_ast.extract_file(suite / "test_things.py")
    plain = [c for c in result["cases"] if "plain_assert" in c["source_test"]]
    assert plain and plain[0]["expected"] == 42
    assert plain[0]["inputs"]["args"] == [21]
    assert plain[0]["inputs"]["callee"] == "double"


def test_ast_carries_class_level_marks(suite: Path) -> None:
    result = static_ast.extract_file(suite / "test_things.py")
    marked = [c for c in result["cases"] if "test_marked" in c["source_test"]]
    assert marked and all("slow" in c["marks"] for c in marked)


# --------------------------------------------------------------------------- #
# the CLI: collection + AST merged, coverage line honest
# --------------------------------------------------------------------------- #

def _run_import(suite: Path, root: Path, method: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ent.cli", "import-tests", str(suite),
         "--method", method, "--root", str(root)],
        capture_output=True, text=True, timeout=300)


def test_collection_catches_computed_and_fixture_params(suite: Path, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    proc = _run_import(suite, root, "both")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = root / "entiendo" / "proposals" / "imported-tests" / "test_things.cases.json"
    cases = json.loads(out.read_text())["cases"]
    # computed parametrize resolved by collection (AST skipped it)
    computed = [c for c in cases if "test_computed" in c["source_test"]]
    assert {c["inputs"]["n"] for c in computed} == {0, 2, 4, 6, 8}
    assert all(c["extraction_method"] == "collect" for c in computed)
    # fixture params resolved too
    colours = [c for c in cases if "test_fixture_param" in c["source_test"]]
    assert {c["inputs"]["colour"] for c in colours} == {"red", "blue"}


def test_network_case_is_flagged_needs_harness_never_extracted(
        suite: Path, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    proc = _run_import(suite, root, "both")
    assert "needs_harness" in proc.stdout
    assert "test_needs_network" in proc.stdout
    out = root / "entiendo" / "proposals" / "imported-tests" / "test_things.cases.json"
    cases = json.loads(out.read_text())["cases"]
    assert not any("needs_network" in c["source_test"] and c.get("inputs")
                   for c in cases)


def test_coverage_line_is_always_printed_and_adds_up(suite: Path, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    proc = _run_import(suite, root, "both")
    line = next(l for l in proc.stdout.splitlines() if l.startswith("extracted"))
    assert "AST:" in line and "collection:" in line
    assert "needs_harness" in line and "non-literal skipped" in line


def test_ast_only_method_never_runs_pytest(suite: Path, tmp_path: Path) -> None:
    """--method ast must work on a suite whose import would explode — the
    static path never executes repo code."""
    (suite / "test_boom.py").write_text(
        "import pytest\nraise RuntimeError('import-time bomb')\n\n"
        "@pytest.mark.parametrize('x', [1])\ndef test_x(x):\n    assert x\n")
    root = tmp_path / "proj"
    root.mkdir()
    proc = _run_import(suite, root, "ast")
    assert proc.returncode == 0
    out = root / "entiendo" / "proposals" / "imported-tests" / "test_boom.cases.json"
    assert json.loads(out.read_text())["cases"]            # extracted anyway

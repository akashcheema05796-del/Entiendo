"""By-name imports inside monorepos must become edges (astrobee gap 3).

astrobee's 43-unit map had ZERO edges: its packages import each other by
installed name (`import localization_common`), which lives at
`localization/localization_common/scripts/localization_common/` — invisible
when resolution only starts at the repo root. Missing edges that look like
decoupling are the worst kind. Resolution now also tries the importing file's
own directory (script-style sys.path) and a repo-wide top-level package map,
refusing ambiguous names rather than guessing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent.languages.python import PythonExtractor, _PKG_CACHE  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_cache():
    _PKG_CACHE.clear()
    yield
    _PKG_CACHE.clear()


def _targets(file: Path, root: Path) -> set[str]:
    return {e.target.relative_to(root.resolve()).as_posix()
            for e in PythonExtractor().resolved_imports(file, root)}


def test_catkin_style_by_name_import_resolves(tmp_path: Path) -> None:
    """`import localization_common` from a distant scripts dir — the astrobee
    shape verbatim."""
    root = tmp_path / "repo"
    pkg = root / "localization" / "localization_common" / "scripts" / "localization_common"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "utilities.py").write_text("def basename(p):\n    return p\n")
    app = root / "tools" / "analysis"
    app.mkdir(parents=True)
    (app / "make_map.py").write_text("import localization_common.utilities\n")

    assert _targets(app / "make_map.py", root) == {
        "localization/localization_common/scripts/localization_common/utilities.py"}


def test_from_import_of_the_package_itself_resolves(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    pkg = root / "src" / "mylib"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    app = root / "app"
    app.mkdir()
    (app / "main.py").write_text("from mylib import thing\n")
    assert _targets(app / "main.py", root) == {"src/mylib/__init__.py"}


def test_sibling_script_import_resolves(tmp_path: Path) -> None:
    """astrobee's localization_analysis scripts import each other bare
    (`import plot_helpers`) — real because a script's own dir joins sys.path."""
    root = tmp_path / "repo"
    d = root / "scripts"
    d.mkdir(parents=True)
    (d / "plot_helpers.py").write_text("def plot():\n    pass\n")
    (d / "plotter.py").write_text("import plot_helpers\n")
    assert _targets(d / "plotter.py", root) == {"scripts/plot_helpers.py"}


def test_ambiguous_package_name_is_refused_not_guessed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    for place in ("a", "b"):
        pkg = root / place / "dup"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
    app = root / "app"
    app.mkdir()
    (app / "main.py").write_text("import dup\n")
    assert _targets(app / "main.py", root) == set()


def test_third_party_imports_stay_external(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    app = root / "app"
    app.mkdir(parents=True)
    (app / "main.py").write_text("import numpy\nimport requests\n")
    assert _targets(app / "main.py", root) == set()


def test_root_resolution_still_wins_over_the_package_map(tmp_path: Path) -> None:
    """The original behaviour is untouched: a root-relative hit resolves
    before any fallback fires."""
    root = tmp_path / "repo"
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "__init__.py").write_text("")
    (root / "lib" / "maths.py").write_text("def double(x):\n    return x * 2\n")
    (root / "app.py").write_text("import lib.maths\n")
    assert _targets(root / "app.py", root) == {"lib/maths.py"}


def test_retrofit_now_proposes_the_cross_package_edge(tmp_path: Path) -> None:
    """End to end: the astrobee shape yields a calls edge at propose time."""
    from ent import retrofit

    root = tmp_path / "repo"
    pkg = root / "vendorland" / "corelib" / "scripts" / "corelib"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "util.py").write_text("def f(x):\n    return x\n")
    app = root / "tools"
    app.mkdir()
    (app / "runner.py").write_text("import corelib.util\n\ndef run(x):\n    return corelib.util.f(x)\n")

    proposals = retrofit.propose(root, probe=False)
    tool = next(p for p in proposals if p.node_id.endswith(".tools"))
    core = next(p for p in proposals if "corelib" in p.node_id)
    assert core.node_id in tool.manifest["dependencies"]["calls"]

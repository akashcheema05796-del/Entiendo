"""Regressions from the 100-repo gauntlet — real-world mess, fixed.

D1  accepting one proposal whose inferred deps point at STAGED SIBLINGS left
    a dangling `unknown node` edge → the partial project failed
    `ent extract --check` (seen on 15/94 repos: httpx, express, chalk, …)
D2  a symlink escaping the repo root (jekyll ships one to /etc/passwd)
    crashed every walk with ValueError in relative_to
D3  an entry the OS cannot stat (trpc's ENAMETOOLONG fixture; symlink loops)
    aborted retrofit with an uncaught OSError
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

import yaml  # noqa: E402

from ent import retrofit  # noqa: E402
from ent.ci import run_ci  # noqa: E402
from ent.extractor import extract  # noqa: E402
from ent.manifest import iter_project_files  # noqa: E402


def _two_module_repo(tmp_path: Path) -> Path:
    """`app.py` imports `lib/maths.py` — retrofit proposes two units with an
    inferred calls edge between them."""
    root = tmp_path / "proj"
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "maths.py").write_text("def double(x):\n    return x * 2\n")
    (root / "app.py").write_text("import lib.maths\n\ndef go(n):\n    return lib.maths.double(n)\n")
    return root


def _staged(root: Path) -> list:
    proposals = retrofit.propose(root)
    retrofit.write_proposals(root, proposals)           # accept reads the stage
    return proposals


# --------------------------------------------------------------------------- #
# D1 — the first manifest must yield a WORKING partial project
# --------------------------------------------------------------------------- #

def test_accepting_one_unit_holds_back_edges_to_staged_siblings(tmp_path: Path) -> None:
    root = _two_module_repo(tmp_path)
    proposals = _staged(root)
    caller = next(p for p in proposals if "app" in p.node_id)
    assert any(c == p.node_id for p in proposals
               for c in (caller.manifest.get("dependencies", {}).get("calls") or [])), \
        "fixture must reproduce the inferred sibling edge"

    dest, held = retrofit.accept(root, caller.node_id)
    manifest = yaml.safe_load(dest.read_text())
    assert not (manifest.get("dependencies", {}).get("calls") or []), \
        "the dangling edge must be held back, not promoted"
    assert held and held[0][0] == "calls"

    # the guarantee the gauntlet caught us breaking: partial project WORKS
    ext = extract(root)
    assert ext.ok, ext.errors
    assert run_ci(root).exit_code == 0


def test_the_reconciler_reraises_the_held_edge_when_the_sibling_arrives(tmp_path: Path) -> None:
    """Held-back is not forgotten: accept the sibling later and the real
    import surfaces as undeclared-dependency drift — the mechanical reminder
    to re-declare the edge."""
    root = _two_module_repo(tmp_path)
    proposals = _staged(root)
    caller = next(p for p in proposals if "app" in p.node_id)
    callee = next(p for p in proposals if "lib" in p.node_id)
    retrofit.accept(root, caller.node_id)
    retrofit.accept(root, callee.node_id)
    ext = extract(root)
    assert not ext.ok
    assert any("undeclared dependency" in e and callee.node_id in e
               for e in ext.errors)


def test_edges_to_already_accepted_units_survive(tmp_path: Path) -> None:
    """Accept callee FIRST: the caller's edge points at a real unit and must
    be kept — holding back is only for units that don't exist yet."""
    root = _two_module_repo(tmp_path)
    proposals = _staged(root)
    caller = next(p for p in proposals if "app" in p.node_id)
    callee = next(p for p in proposals if "lib" in p.node_id)
    retrofit.accept(root, callee.node_id)
    dest, held = retrofit.accept(root, caller.node_id)
    manifest = yaml.safe_load(dest.read_text())
    assert callee.node_id in (manifest["dependencies"].get("calls") or [])
    assert not held
    assert extract(root).ok


# --------------------------------------------------------------------------- #
# D2 — symlinks escaping the root are never followed, never fatal
# --------------------------------------------------------------------------- #

def test_symlink_escaping_the_root_is_skipped_not_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside-secret.py"
    outside.write_text("STOLEN = True\n")
    root = _two_module_repo(tmp_path)
    (root / "lib" / "escape.py").symlink_to(outside)

    walked = {p.name for p in iter_project_files(root)}
    assert "escape.py" not in walked                    # never treated as ours

    proposals = _staged(root)                           # jekyll crashed here
    claimed = [c for p in proposals for c in p.manifest.get("claims", [])]
    assert "lib/escape.py" not in claimed
    caller = next(p for p in proposals if "app" in p.node_id)
    retrofit.accept(root, caller.node_id)
    assert extract(root).ok                             # …and here
    assert run_ci(root).exit_code == 0


def test_inroot_symlinks_are_still_project_files(tmp_path: Path) -> None:
    """Only ESCAPING symlinks are hostile — a link to a sibling inside the
    root is an ordinary aliasing pattern and stays visible."""
    root = _two_module_repo(tmp_path)
    (root / "alias.py").symlink_to(root / "app.py")
    walked = {p.name for p in iter_project_files(root)}
    assert "alias.py" in walked


# --------------------------------------------------------------------------- #
# D3 — entries the OS cannot stat are skipped, never fatal
# --------------------------------------------------------------------------- #

def test_unstatable_entries_do_not_abort_the_walk(tmp_path: Path) -> None:
    root = _two_module_repo(tmp_path)
    loop = root / "lib" / "loop.py"
    loop.symlink_to(loop)                               # ELOOP on stat — like
    walked = list(iter_project_files(root))             # trpc's ENAMETOOLONG
    assert all(p.name != "loop.py" for p in walked)
    proposals = _staged(root)                           # trpc aborted here
    assert proposals
    caller = next(p for p in proposals if "app" in p.node_id)
    retrofit.accept(root, caller.node_id)
    assert extract(root).ok
    assert run_ci(root).exit_code == 0


def test_garbage_ts_specifier_resolves_to_nothing_never_crashes(tmp_path: Path) -> None:
    """trpc's actual failure: the regex pass mistook import-like text inside
    a template string for a specifier, built an ENAMETOOLONG candidate path,
    and exists() blew up. A garbage specifier resolves to nothing."""
    from ent.languages.typescript import TypeScriptExtractor
    root = tmp_path / "ts"
    root.mkdir()
    huge = "./" + "x" * 4000
    (root / "a.ts").write_text(
        f"const snippet = `import x from '{huge}'`;\nexport const a = 1;\n")
    assert TypeScriptExtractor().resolved_imports(root / "a.ts", root) == []


def test_nameless_specifier_resolves_to_nothing(tmp_path: Path) -> None:
    """webpack's actual failure: a '/' specifier produced a base path with no
    name, and with_suffix() raised ValueError mid-retrofit."""
    from ent.languages.typescript import TypeScriptExtractor
    root = tmp_path / "ts"
    root.mkdir()
    (root / "a.ts").write_text("const x = require('/');\nimport y from '.';\n"
                               "export const a = 1;\n")
    assert TypeScriptExtractor().resolved_imports(root / "a.ts", root) == []


def test_unreadable_python_file_never_crashes_the_extractor(tmp_path: Path) -> None:
    """spring-boot flavour: a claimed .py path that cannot be opened (broken
    link, vanished file) yields no imports instead of an OSError."""
    from ent.languages.python import PythonExtractor
    root = tmp_path / "py"
    root.mkdir()
    gone = root / "gone.py"
    gone.symlink_to(root / "never-existed.py")
    assert PythonExtractor().resolved_imports(gone, root) == []


def test_accept_time_eval_is_sandboxed_against_hostile_imports(tmp_path: Path) -> None:
    """node.js's actual failure: the accepted unit's proposed entrypoint was a
    script that argparses and sys.exit()s AT IMPORT — run in-process it killed
    the accept command. The eval must run in the bounded sandbox child: accept
    exits 0, the verdict line prints, and the hostile module's exit code never
    becomes ours."""
    import subprocess
    import sys as _sys
    root = tmp_path / "proj"
    root.mkdir()
    (root / "configure.py").write_text(
        "import sys\nprint('Usage: ./configure <args>')\nsys.exit(2)\n")
    (root / "lib").mkdir()
    (root / "lib" / "ok.py").write_text("def f(x):\n    return x\n")

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([_sys.executable, "-m", "ent.cli", *args],
                              cwd=str(root), capture_output=True, text=True,
                              timeout=180)

    assert run("retrofit", ".").returncode == 0
    unit = "proj.configure"
    proc = run("retrofit", ".", "--accept", unit)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"eval: {unit} →" in proc.stdout             # the flow completed

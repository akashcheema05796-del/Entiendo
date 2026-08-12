"""AST test-case extractor — never executes repo code (Phase 4, method 'ast').

Extracts only what is provably literal:

  - `@pytest.mark.parametrize("a,b", [...])` argvalues via ast.literal_eval —
    anything computed (`[i*2 for i in range(5)]`, function calls, names) is
    SKIPPED and counted, never evaluated;
  - `pytest.param(..., id=...)` ids become case names; `marks=pytest.mark.
    xfail/skip` become case metadata;
  - simple `assert f(<literals>) == <literal>` statements in test bodies.

The safety contract: this pass can under-extract, but it can never emit an
evaluated (hence possibly wrong) value.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from . import case


def _literal(node: ast.AST) -> tuple[bool, Any]:
    try:
        return True, ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return False, None


def _param_entry(node: ast.AST) -> tuple[bool, Any, str | None, list[str]]:
    """(is_literal, value(s), explicit_id, marks) for one argvalues entry —
    handles both plain literals and pytest.param(...)."""
    if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("pytest.param"):
        values = []
        for arg in node.args:
            ok, v = _literal(arg)
            if not ok:
                return False, None, None, []
            values.append(v)
        pid, marks = None, []
        for kw in node.keywords:
            if kw.arg == "id":
                ok, v = _literal(kw.value)
                pid = v if ok else None
            if kw.arg == "marks":
                marks = [m for m in ("xfail", "skip", "skipif")
                         if m in ast.unparse(kw.value)]
        return True, (values[0] if len(values) == 1 else values), pid, marks
    ok, v = _literal(node)
    return ok, v, None, []


def _names(argnames: ast.AST) -> list[str] | None:
    ok, v = _literal(argnames)
    if not ok:
        return None
    if isinstance(v, str):
        return [s.strip() for s in v.split(",")]
    if isinstance(v, (list, tuple)):
        return [str(s) for s in v]
    return None


def _module_marks(tree: ast.Module) -> list[str]:
    """Module-level `pytestmark = pytest.mark.x` (or a list of them)."""
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            out.extend(m for m in ("xfail", "skip", "network", "slow")
                       if m in ast.unparse(node.value))
    return out


def _class_marks(cls: ast.ClassDef) -> list[str]:
    out: list[str] = []
    for node in cls.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            out.extend(m for m in ("xfail", "skip", "network", "slow")
                       if m in ast.unparse(node.value))
    return out


def extract_file(path: Path) -> dict[str, Any]:
    """{'cases': [...], 'skipped_non_literal': int} for one test module."""
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError, OSError):
        return {"cases": [], "skipped_non_literal": 0}

    cases: list[dict[str, Any]] = []
    skipped = 0
    base_marks = _module_marks(tree)

    def visit_function(fn: ast.FunctionDef, extra_marks: list[str]) -> None:
        nonlocal skipped
        fn_marks = list(dict.fromkeys(base_marks + extra_marks))
        for deco in fn.decorator_list:
            if not (isinstance(deco, ast.Call)
                    and ast.unparse(deco.func).endswith("parametrize")
                    and len(deco.args) >= 2):
                continue
            names = _names(deco.args[0])
            values_node = deco.args[1]
            if names is None or not isinstance(values_node, (ast.List, ast.Tuple)):
                skipped += 1                    # whole computed argvalues list
                continue
            for i, entry in enumerate(values_node.elts):
                ok, value, pid, pmarks = _param_entry(entry)
                if not ok:
                    skipped += 1                # one non-literal row
                    continue
                row = value if len(names) > 1 else [value]
                if len(names) > 1 and (not isinstance(row, (list, tuple))
                                       or len(row) != len(names)):
                    skipped += 1
                    continue
                inputs = dict(zip(names, row))
                cases.append(case(
                    source_test=f"{path.name}::{fn.name}",
                    case_id=pid or f"{fn.name}[{i}]",
                    inputs=inputs, expected=inputs.pop("expected", None),
                    marks=list(dict.fromkeys(fn_marks + pmarks)),
                    method="ast", confidence="high"))
        # assert f(<literals>) == <literal>
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Assert)
                    and isinstance(node.test, ast.Compare)
                    and len(node.test.ops) == 1
                    and isinstance(node.test.ops[0], ast.Eq)):
                continue
            left, right = node.test.left, node.test.comparators[0]
            if not isinstance(left, ast.Call):
                continue
            ok_r, expected = _literal(right)
            args_ok, args = True, []
            for a in left.args:
                ok_a, v = _literal(a)
                if not ok_a:
                    args_ok = False
                    break
                args.append(v)
            if ok_r and args_ok:
                cases.append(case(
                    source_test=f"{path.name}::{fn.name}",
                    case_id=f"{fn.name}:assert@{node.lineno}",
                    inputs={"args": args,
                            "callee": ast.unparse(left.func)},
                    expected=expected,
                    marks=fn_marks, method="ast", confidence="high"))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name.startswith("test"):
            visit_function(node, [])
        if isinstance(node, ast.ClassDef):
            cmarks = _class_marks(node)
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and sub.name.startswith("test"):
                    visit_function(sub, cmarks)

    return {"cases": cases, "skipped_non_literal": skipped}


def extract_path(path: Path) -> dict[str, dict[str, Any]]:
    """Every test module under `path` → its extraction result."""
    path = Path(path)
    files = [path] if path.is_file() else sorted(
        [*path.rglob("test_*.py"), *path.rglob("*_test.py")])
    return {str(f): extract_file(f) for f in files}

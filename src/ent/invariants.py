"""Restricted evaluation of contract invariants (Phase 7 §4).

Invariants are Python expressions over exactly two names, `input` and `output`.
Manifests are frequently AI-authored, so this is an arbitrary-code-execution
surface — **we never call eval() or compile+exec**. Instead:

  - `validate_invariant` parses with `ast.parse(mode="eval")` and rejects any
    node type, name, call target, or dunder access outside a strict allowlist.
    Bad invariants fail at `ent validate` time, before they ever run.
  - `eval_invariant` walks the (already-validated) tree with a tiny interpreter.
    There is no code object and no exec — a rejected construct simply has no
    interpreter branch. Attribute access on dicts resolves as key access, so
    `output.chunks` means `output["chunks"]`.

Allowlist by node *type* (never a blocklist — unknown ⇒ rejected).
"""

from __future__ import annotations

import ast
from typing import Any

_ALLOWED_NODES = (
    ast.Expression, ast.Compare, ast.BoolOp, ast.UnaryOp, ast.BinOp,
    ast.Constant, ast.Name, ast.Attribute, ast.Subscript, ast.Call,
    ast.GeneratorExp, ast.ListComp, ast.SetComp, ast.comprehension,
    ast.List, ast.Tuple, ast.Dict, ast.Load, ast.Store,
    # operators
    ast.And, ast.Or, ast.Not, ast.USub, ast.UAdd,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
    ast.Index if hasattr(ast, "Index") else ast.Load,  # py<3.9 compat, harmless
)

_ALLOWED_BUILTINS = {
    "len": len, "all": all, "any": any, "abs": abs, "sum": sum, "min": min,
    "max": max, "sorted": sorted, "isinstance": isinstance, "round": round,
    "str": str, "int": int, "float": float, "bool": bool,
    # types usable as isinstance() targets
    "list": list, "dict": dict, "tuple": tuple, "set": set,
    # bytes-oriented units (codecs, signers, parsers) must be able to assert
    # their own output type — str was allowed but bytes was not.
    "bytes": bytes, "bytearray": bytearray, "frozenset": frozenset,
}

_BASE_NAMES = {"input", "output"}


class InvariantError(ValueError):
    """A malformed or disallowed invariant expression."""


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #

def validate_invariant(expr: str) -> None:
    """Raise InvariantError if `expr` uses anything outside the allowlist."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise InvariantError(f"not a valid expression: {exc.msg}")

    bound = _comprehension_vars(tree)
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise InvariantError(f"disallowed syntax: {type(node).__name__}")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise InvariantError(f"disallowed attribute '{node.attr}' (underscore)")
        if isinstance(node, ast.Name):
            if node.id not in _BASE_NAMES and node.id not in _ALLOWED_BUILTINS and node.id not in bound:
                raise InvariantError(f"disallowed name '{node.id}' (only input, output, builtins)")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_BUILTINS:
                raise InvariantError("only calls to the builtin allowlist are permitted")
            if node.keywords:
                raise InvariantError("keyword arguments are not permitted in invariants")


def _comprehension_vars(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.comprehension):
            for t in ast.walk(node.target):
                if isinstance(t, ast.Name):
                    names.add(t.id)
    return names


# --------------------------------------------------------------------------- #
# evaluation (tree-walking interpreter — no eval/exec)
# --------------------------------------------------------------------------- #

def eval_invariant(expr: str, input: Any, output: Any) -> tuple[bool, str]:
    """Evaluate `expr` against input/output.

    Returns (passed, detail). On failure, detail shows the operand values so the
    message is useful: `len(output.chunks)=12 <= input.k=5`.
    """
    tree = ast.parse(expr, mode="eval")
    env = {"input": input, "output": output}
    result = _ev(tree.body, env)
    passed = bool(result)
    if passed:
        return True, expr
    return False, _explain(tree.body, env)


_CMP = {
    ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b,
    ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
}
_BIN = {
    ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b,
}


def _ev(node: ast.AST, env: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        if node.id in _ALLOWED_BUILTINS:
            return _ALLOWED_BUILTINS[node.id]
        raise InvariantError(f"name '{node.id}' is not defined")
    if isinstance(node, ast.Attribute):
        obj = _ev(node.value, env)
        if node.attr.startswith("_"):
            raise InvariantError(f"disallowed attribute '{node.attr}'")
        if isinstance(obj, dict):
            return obj[node.attr]
        return getattr(obj, node.attr)
    if isinstance(node, ast.Subscript):
        obj = _ev(node.value, env)
        key = _ev(node.slice.value if hasattr(node.slice, "value") and isinstance(node.slice, ast.Index) else node.slice, env)
        return obj[key]
    if isinstance(node, ast.Compare):
        left = _ev(node.left, env)
        for op, comp in zip(node.ops, node.comparators):
            right = _ev(comp, env)
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        vals = (_ev(v, env) for v in node.values)
        if isinstance(node.op, ast.And):
            return all(vals)
        return any(vals)
    if isinstance(node, ast.UnaryOp):
        val = _ev(node.operand, env)
        if isinstance(node.op, ast.Not):
            return not val
        if isinstance(node.op, ast.USub):
            return -val
        return +val
    if isinstance(node, ast.BinOp):
        return _BIN[type(node.op)](_ev(node.left, env), _ev(node.right, env))
    if isinstance(node, ast.Call):
        fn = _ALLOWED_BUILTINS[node.func.id]  # validated
        return fn(*[_ev(a, env) for a in node.args])
    if isinstance(node, (ast.List, ast.Tuple)):
        vals = [_ev(e, env) for e in node.elts]
        return tuple(vals) if isinstance(node, ast.Tuple) else vals
    if isinstance(node, ast.Dict):
        return {_ev(k, env): _ev(v, env) for k, v in zip(node.keys, node.values)}
    if isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
        return list(_iter_comp(node, env))
    raise InvariantError(f"cannot evaluate {type(node).__name__}")


def _iter_comp(node: ast.AST, env: dict[str, Any]):
    (gen,) = node.generators
    iterable = _ev(gen.iter, env)
    for item in iterable:
        local = dict(env)
        _bind(gen.target, item, local)
        if all(_ev(c, local) for c in gen.ifs):
            yield _ev(node.elt, local)


def _bind(target: ast.AST, value: Any, env: dict[str, Any]) -> None:
    if isinstance(target, ast.Name):
        env[target.id] = value
    elif isinstance(target, (ast.Tuple, ast.List)):
        for t, v in zip(target.elts, value):
            _bind(t, v, env)


def _explain(node: ast.AST, env: dict[str, Any]) -> str:
    """Best-effort operand values for a failed Compare."""
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        left_src = ast.unparse(node.left)
        right_src = ast.unparse(node.comparators[0])
        op_src = ast.unparse(node).split(left_src, 1)[-1].rsplit(right_src, 1)[0].strip()
        try:
            lval = _ev(node.left, env)
            rval = _ev(node.comparators[0], env)
            return f"{left_src}={lval!r} {op_src} {right_src}={rval!r}"
        except Exception:
            pass
    return f"{ast.unparse(node)} is falsey"

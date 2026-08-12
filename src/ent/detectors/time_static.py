"""Static clock-dependency detector — AST pass + transitive propagation.

Flags every construct that makes output depend on WHEN it ran:

    datetime.now/utcnow/today · date.today · time.time/monotonic/localtime
    pd.Timestamp.now · uuid.uuid1 · unseeded random.* · os.environ['TZ']

then builds an intra-project call graph over all claimed .py files and
propagates the flag transitively — a unit calling a clock-touching helper
two files away is flagged, with the call chain as evidence.

Static analysis is necessary but insufficient (a seasonal `month == 12`
branch passes any static filter you can afford) — the dynamic pass
(time_dynamic.py) is the confirming instrument. Findings here are marked
`static` so reports never conflate suspicion with observation.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# (qualified-call suffix, why it ties output to the clock)
_CLOCK_CALLS: dict[str, str] = {
    "datetime.now": "reads the wall clock",
    "datetime.utcnow": "reads the wall clock (UTC)",
    "datetime.today": "reads the wall clock",
    "date.today": "reads today's date",
    "time.time": "reads the epoch clock",
    "time.monotonic": "reads the monotonic clock",
    "time.localtime": "reads the local clock + timezone",
    "time.gmtime": "reads the clock",
    "time.strftime": "formats the current time when called without a struct",
    "Timestamp.now": "pandas wall-clock read",
    "uuid.uuid1": "uuid1 embeds the host clock",
}
_RANDOM_FUNCS = {"random", "randint", "randrange", "choice", "choices",
                 "shuffle", "sample", "uniform", "gauss"}


@dataclass
class Finding:
    file: str
    line: int
    what: str
    why: str
    via: tuple[str, ...] = ()          # call chain for transitive findings

    def evidence(self) -> str:
        chain = f" (via {' → '.join(self.via)})" if self.via else ""
        return f"{self.file}:{self.line} {self.what} — {self.why}{chain}"


@dataclass
class _Module:
    rel: str
    tree: ast.AST
    seeds_random: bool = False
    # function name (qualified module-locally) -> direct clock findings
    func_findings: dict[str, list[Finding]] = field(default_factory=dict)
    # function -> called names (bare and dotted tails, best-effort)
    calls: dict[str, set[str]] = field(default_factory=dict)
    # names this module imports -> the module they come from (best-effort)
    imports: dict[str, str] = field(default_factory=dict)


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _direct_findings(rel: str, call: ast.Call, seeds_random: bool) -> Finding | None:
    name = _dotted(call.func)
    tail2 = ".".join(name.split(".")[-2:])
    if tail2 in _CLOCK_CALLS:
        return Finding(rel, call.lineno, tail2, _CLOCK_CALLS[tail2])
    parts = name.split(".")
    if not seeds_random and len(parts) == 2 and parts[0] == "random" \
            and parts[1] in _RANDOM_FUNCS:
        return Finding(rel, call.lineno, name, "unseeded randomness")
    return None


def _tz_env_findings(rel: str, tree: ast.AST) -> list[Finding]:
    out: list[Finding] = []
    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.Subscript) and _dotted(node.value).endswith("os.environ"):
            target = node.slice
        elif isinstance(node, ast.Call) and _dotted(node.func).endswith("os.environ.get"):
            target = node.args[0] if node.args else None
        if target is not None and isinstance(target, ast.Constant) and target.value == "TZ":
            out.append(Finding(rel, node.lineno, "os.environ['TZ']",
                               "output depends on the process timezone"))
    return out


def _parse_module(root: Path, rel: str) -> _Module | None:
    try:
        tree = ast.parse((root / rel).read_text())
    except (SyntaxError, UnicodeDecodeError, OSError, ValueError):
        return None
    mod = _Module(rel=rel, tree=tree)
    mod.seeds_random = any(
        isinstance(n, ast.Call) and _dotted(n.func) in ("random.seed", "seed")
        for n in ast.walk(tree))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                mod.imports[alias.asname or alias.name.split(".")[0]] = \
                    getattr(node, "module", None) or alias.name

    module_level = "<module>"
    mod.func_findings[module_level] = []
    mod.calls[module_level] = set()

    class V(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = [module_level]

        def _fn(self) -> str:
            return self.stack[-1]

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.stack.append(node.name)
            mod.func_findings.setdefault(node.name, [])
            mod.calls.setdefault(node.name, set())
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

        def visit_Call(self, node: ast.Call) -> None:
            f = _direct_findings(rel, node, mod.seeds_random)
            if f is not None:
                mod.func_findings[self._fn()].append(f)
            name = _dotted(node.func)
            if name:
                mod.calls[self._fn()].add(name.split(".")[-1])
                mod.calls[self._fn()].add(name)
            self.generic_visit(node)

    V().visit(tree)
    for f in _tz_env_findings(rel, tree):
        mod.func_findings[module_level].append(f)
    return mod


def analyze(root: Path, files_by_unit: dict[str, list[str]]) -> dict[str, dict]:
    """Per-unit report: {unit: {time_pure, findings: [evidence...], grade}}.

    `files_by_unit` maps unit id -> claimed .py files (repo-relative). The
    call graph spans ALL provided files, so cross-unit helpers propagate.
    """
    root = Path(root)
    modules: dict[str, _Module] = {}
    for files in files_by_unit.values():
        for rel in files:
            if rel.endswith(".py") and rel not in modules:
                m = _parse_module(root, rel)
                if m is not None:
                    modules[rel] = m

    # function universe: (rel, fname) -> findings; plus name index for edges
    tainted: dict[tuple[str, str], list[Finding]] = {}
    by_name: dict[str, list[tuple[str, str]]] = {}
    for rel, mod in modules.items():
        for fname, finds in mod.func_findings.items():
            by_name.setdefault(fname, []).append((rel, fname))
            if finds:
                tainted[(rel, fname)] = finds

    # propagate to fixpoint: caller inherits callee's findings (with the chain)
    changed = True
    while changed:
        changed = False
        for rel, mod in modules.items():
            for fname, called in mod.calls.items():
                key = (rel, fname)
                for cname in called:
                    for target in by_name.get(cname.split(".")[-1], []):
                        if target == key or target not in tainted:
                            continue
                        inherited = [
                            Finding(f.file, f.line, f.what, f.why,
                                    via=(fname, *((f.via and f.via) or (target[1],))))
                            for f in tainted[target]]
                        current = {(f.file, f.line, f.what) for f in tainted.get(key, [])}
                        new = [f for f in inherited
                               if (f.file, f.line, f.what) not in current]
                        if new:
                            tainted.setdefault(key, []).extend(new)
                            changed = True

    report: dict[str, dict] = {}
    for unit, files in files_by_unit.items():
        finds: list[Finding] = []
        for rel in files:
            mod = modules.get(rel)
            if mod is None:
                continue
            for fname in mod.func_findings:
                finds.extend(tainted.get((rel, fname), []))
        seen: set[str] = set()
        evidence = [e for f in finds if (e := f.evidence()) not in seen
                    and not seen.add(e)]
        report[unit] = {
            "time_pure": not evidence,
            "grade": "static",
            "findings": evidence,
        }
    return report


def claimed_py(root: Path, node: object) -> list[str]:
    from ..claims import expand_claims
    return [c for c in expand_claims(root, getattr(node, "claims", []))
            if c.endswith(".py")]


def analyze_units(root: Path, nodes: Iterable[object]) -> dict[str, dict]:
    return analyze(Path(root), {n.id: claimed_py(root, n) for n in nodes})

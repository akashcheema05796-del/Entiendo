"""`ent doctor` — self-diagnosis of the environment and (optionally) the project.

The first-run gap (gap analysis §4/§6): nothing told you whether your environment
could actually run Entiendo — Python version, the core + optional deps, the model
API key, the schema, the language extractors — nor whether the project you're
standing in reconciles. `ent doctor` answers all of that in one checklist.

`diagnose(root)` is a pure function returning structured `Check`s so it is tested
without a socket or a subprocess; the CLI just prints them and maps the worst
level to an exit code.

Exit codes:
  0  no failures (warnings are fine)
  1  at least one hard failure (a core dep or the schema is broken)

Invariant 6: the model API key is reported present/absent by name only — its
value is never read or rendered.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path

OK, WARN, FAIL = "ok", "warn", "fail"
_MARK = {OK: "✓", WARN: "⚠", FAIL: "✗"}

MIN_PYTHON = (3, 9)
# The env var the editing model reads (agent.py). Reported by name only.
MODEL_KEY_ENV = "ANTHROPIC_API_KEY"


@dataclass(frozen=True)
class Check:
    level: str      # ok | warn | fail
    name: str
    detail: str


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def diagnose(root: Path) -> list[Check]:
    """Run every environment + project check and return them in report order."""
    checks: list[Check] = []
    checks.append(_python_check())
    checks.extend(_core_dep_checks())
    checks.extend(_optional_extra_checks())
    checks.append(_model_key_check())
    checks.append(_schema_check())
    checks.append(_languages_check())
    checks.extend(_project_checks(root))
    return checks


def _python_check() -> Check:
    v = sys.version_info
    cur = f"{v.major}.{v.minor}.{v.micro}"
    need = ".".join(map(str, MIN_PYTHON))
    if (v.major, v.minor) >= MIN_PYTHON:
        return Check(OK, "python", f"{cur} (>= {need})")
    return Check(FAIL, "python", f"{cur} — Entiendo needs Python >= {need}")


def _core_dep_checks() -> list[Check]:
    out = []
    for mod, extra in (("yaml", "pyyaml"), ("jsonschema", "jsonschema")):
        if _has(mod):
            out.append(Check(OK, f"dep:{extra}", "installed"))
        else:
            out.append(Check(FAIL, f"dep:{extra}",
                             f"missing — required. Try: pip install -e '.[dev]'"))
    return out


def _optional_extra_checks() -> list[Check]:
    # (import name, extra name, what it unlocks)
    optional = [
        ("anthropic", "serve", "the editing model behind `ent serve` / `ent edit`"),
        ("mcp", "mcp", "`ent mcp` (MCP tools for Claude Code)"),
        ("pytest", "dev", "the test suite"),
    ]
    out = []
    for mod, extra, unlocks in optional:
        if _has(mod):
            out.append(Check(OK, f"extra:{extra}", f"installed — {unlocks}"))
        else:
            out.append(Check(WARN, f"extra:{extra}",
                             f"not installed — {unlocks}. Add with: pip install -e '.[{extra}]'"))
    return out


def _model_key_check() -> Check:
    # Presence only — never read the value (Invariant 6: secrets are reference-only).
    if os.environ.get(MODEL_KEY_ENV):
        return Check(OK, "model-key", f"{MODEL_KEY_ENV} is set (value not read)")
    return Check(WARN, "model-key",
                 f"{MODEL_KEY_ENV} not set — steering with the built-in model is off "
                 "(the explorer, evals, and the Bridge operator still work)")


def _schema_check() -> Check:
    try:
        from ..schema import build_validator, load_schema
        schema = load_schema()
        build_validator()  # constructs + checks the Draft 2020-12 validator
        api = schema.get("$comment") or schema.get("title") or "node.schema.json"
        return Check(OK, "schema", f"loads + validator builds ({api})")
    except ModuleNotFoundError as exc:
        return Check(FAIL, "schema", f"cannot load — missing dependency: {exc}")
    except Exception as exc:                       # a broken schema is a hard fail
        return Check(FAIL, "schema", f"invalid: {exc}")


def _languages_check() -> Check:
    try:
        from .. import languages
        names = sorted({languages.for_file(Path(f"x{e}")).name
                        for e in languages.extensions()})
        exts = ", ".join(sorted(languages.extensions()))
        return Check(OK, "languages", f"{', '.join(names)} ({exts})")
    except Exception as exc:                       # pragma: no cover - defensive
        return Check(WARN, "languages", f"registry unavailable: {exc}")


def _project_checks(root: Path) -> list[Check]:
    """If `root` is an Entiendo project, report whether it reconciles."""
    try:
        from ..manifest import discover
    except ModuleNotFoundError:
        return []                                  # covered by the core-dep fail
    manifests = discover(root)
    if not manifests:
        return [Check(OK, "project",
                      f"no units under {root} — run `ent init` to start one")]

    out = [Check(OK, "project", f"{len(manifests)} unit(s) under {root}")]

    try:
        from ..validation import validate_root
        report = validate_root(root)
        out.append(Check(OK if report.ok else FAIL, "validate",
                         "all manifests valid" if report.ok
                         else "manifest validation failed — run `ent validate`"))
    except Exception as exc:
        out.append(Check(WARN, "validate", f"could not run: {exc}"))

    try:
        from ..extractor import extract
        result = extract(root)
        cov = result.coverage.get("coverage")
        if result.ok:
            out.append(Check(OK, "reconcile",
                             f"graph reconciles, coverage {cov:.0%}" if cov is not None
                             else "graph reconciles"))
        else:
            out.append(Check(FAIL, "reconcile",
                             f"{len(result.errors)} drift/structural error(s) — run `ent extract`"))
    except Exception as exc:
        out.append(Check(WARN, "reconcile", f"could not run: {exc}"))

    return out


def worst_level(checks: list[Check]) -> str:
    if any(c.level == FAIL for c in checks):
        return FAIL
    if any(c.level == WARN for c in checks):
        return WARN
    return OK


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def register(subparsers: "argparse._SubParsersAction") -> None:
    p = subparsers.add_parser(
        "doctor",
        help="self-diagnose the environment + project (deps, key, schema, reconcile)",
        description="Check that Entiendo can run here, and that this project reconciles.",
    )
    p.add_argument(
        "--root",
        default=".",
        help="project root to check (default: current directory)",
    )
    p.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    checks = diagnose(root)

    width = max((len(c.name) for c in checks), default=0)
    print("entiendo doctor\n")
    for c in checks:
        print(f"  {_MARK[c.level]} {c.name.ljust(width)}  {c.detail}")

    worst = worst_level(checks)
    print()
    if worst == FAIL:
        print("✗ environment or project has failures — fix the ✗ lines above.")
        return 1
    if worst == WARN:
        print("⚠ usable, with optional pieces missing (the ⚠ lines are safe to ignore).")
        return 0
    print("✓ all good.")
    return 0

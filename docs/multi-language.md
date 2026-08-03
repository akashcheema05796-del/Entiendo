# Multi-language extraction — the seam (spike)

**Status:** design + a working TypeScript/JS proof-of-concept. The Python path is
unchanged; TS resolution is intentionally minimal. See the gap analysis §1.

## The problem

The reconciler (L1, `ent extract`) is Entiendo's anti-drift mechanism: it derives
the *actual* import edges between units and fails the build when reality diverges
from the declared `dependencies` (Invariant 5). Until now that derivation was
Python-only — `ast.parse` + Python module resolution baked into `extractor.py`.
That made the whole control plane Python-only, which is the single largest
structural ceiling for a real polyglot service.

## The seam

Only **one** step in the reconciler is language-specific: *given a source file,
which other files in the project does it import?* Everything downstream — mapping
a file to its owning unit, building unit→unit edges, reconciling declared vs
verified, the interior-tool registry check, coverage — is language-neutral.

So that step is the seam (`src/ent/languages/`):

```
languages/
  base.py         ImportEdge + the LanguageExtractor protocol
  python.py       PythonExtractor  — the original logic, moved, unchanged
  typescript.py   TypeScriptExtractor — the spike
  __init__.py     registry: for_file(path) -> extractor | None
```

```python
class LanguageExtractor(Protocol):
    name: str
    extensions: tuple[str, ...]
    def resolved_imports(self, file: Path, root: Path) -> list[ImportEdge]: ...

@dataclass(frozen=True)
class ImportEdge:
    target: Path   # resolved, intra-project file
    detail: str    # the specifier as written — becomes edge evidence
```

The reconciler asks `languages.for_file(claim)` for an extractor and, if it gets
one, records a verified edge to the owning unit of each `ImportEdge.target`. A
file with no registered extractor (`.md`, `.yaml`, …) is skipped. **The Python
path is byte-for-byte identical** to before the seam — the full suite (251 prior
tests) stays green, and `_ownership` / `_build_edges` / drift are untouched.

Adding a language is adding one file and registering it. `retrofit.py` (which
infers dependencies the same way) also runs through the seam, so retrofit became
language-neutral for free.

## The TypeScript/JS spike

`TypeScriptExtractor` handles `.ts .tsx .mts .cts .js .jsx .mjs .cjs`. It is
dependency-free by design (the project keeps runtime deps minimal — no TS
parser): it finds import **specifiers** with a few regexes and resolves the
**relative** ones to a project file.

Covered import forms:

| Form | Example |
|---|---|
| default / named / namespace | `import x from './m'`, `import { a } from '../lib/m'`, `import * as n from './m'` |
| side-effect | `import './m'` |
| re-export | `export { a } from './m'`, `export * from './m'` |
| require / dynamic | `require('./m')`, `await import('./m')` |

Resolution mirrors Node/TS enough for real relative imports: try the specifier
with each source extension, then a directory `index.*`, and map a written
`.js`/`.mjs` specifier onto a `.ts` source (the TS convention). Bare specifiers
(`react`, `@scope/pkg`) are external and dropped; anything resolving outside the
project is dropped.

## tsconfig path aliases (landed)

Non-relative specifiers now resolve through `tsconfig.json`: `paths` aliases
(`@app/*` → `src/*`, or an exact `@lib` → a named file) and `baseUrl`-relative
imports (`utils/x` under `baseUrl: ./src`). Genuine external packages match no
alias and resolve to no project file, so they stay dropped; a project with no
tsconfig is unchanged. tsconfig is read with light JSONC tolerance (comments +
trailing commas); `extends` chains aren't followed yet. See
`tests/test_ts_tsconfig.py`.

## Blind spots — absence of an edge is not proof of no dependency (v6 3.5)

Static import analysis only sees what is written as an import. It is blind to
dynamic imports (`importlib.import_module`, `__import__`), string-keyed
dispatch (`getattr(mod, "name")`), and anything that leaves the process
(`subprocess`, `requests`, `httpx`, `urllib`). `ent extract` now runs a
heuristic pass over claimed Python files and flags these constructs as
`possibleUndeclaredDynamicDep` entries in `graph.json` — printed by the CLI
and shown in the unit's dossier. They are **warnings, never failures**: the
point is honesty about what the extractor cannot see, not a new gate.

For the same reason, edges derived by the TypeScript regex spike carry
`verificationSource: "ts-poc"` instead of `"import"` and render
declared-grade (dashed) in the Universe — a PoC's evidence must not look
compiler-verified.

## Deliberately out of scope (where a real implementation goes next)

The spike proves the seam, not a production TS story. In priority order:

1. **A real tokenizer** — the regex can match import-like text inside comments or
   string literals. A lightweight scanner that skips comments/strings removes
   that ambiguity (still no heavy dependency). `tsconfig` `extends` chains too.
2. **Entrypoint + instrumentation** — L2 (`@ent.node()`), the restricted-AST
   invariant evaluator, and `contract.entrypoint` execution are still
   Python-only. A TS unit can be reconciled and drawn today, but not yet
   *executed* for tier0. That is the next language-agnostic seam to open.
4. **More languages** — the same `LanguageExtractor` shape should carry Go, Rust,
   etc.; each is one module.

## Try it

```python
from ent import languages
languages.for_file(Path("src/app.ts")).resolved_imports(Path("src/app.ts"), root)
```

Tests: `tests/test_ts_extractor.py` (resolution of every import form + two
end-to-end `extract()` reconciliations over a TypeScript project).

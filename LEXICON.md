# Entiendo — Lexicon

The words the product speaks. Every term SPEC.md uses is defined here; the CLI,
the Universe, and the docs use these names (Phase G makes the rename mechanical).

> **Compatibility.** The vocabulary changed in v3; the *format* did not. The
> manifest filename stays `entiendo.node.yaml`, the `claims:` key is unchanged,
> and `apiVersion: entiendo/v1` is untouched (a schema bump is a separate,
> deliberate decision). Old CLI command names keep working with a deprecation
> note. Renaming is a naming change, not a breaking one.

---

## The category

**Control plane** — what Entiendo *is*. Manifests hold the declared desired
state; a reconciler continuously verifies reality against it; evals are the
health probes; fingerprints are the versioned identities; the Universe is the
surface humans steer through. Borrowed deliberately from orchestration systems:
a control plane declares intent and drives reality toward it, out of the request
path.

**Operator** — the human. Steers, approves, blesses. Does not manipulate text.

**Workload** — the coding agent (e.g. Claude Code). Edits *through* units under
the plane's boundaries; never the thing a human hand-types.

**The law** — v3's one axiom. *A boundary is a valid Logical Unit iff it can be
evaluated independently on given data* — from its own artifacts plus its
neighbours' contracts, never their interiors. Not evaluable alone → not a unit →
boundary error. The law is the test every proposed boundary must pass.

---

## The primitive

**Unit** (Logical Unit) — the atom of work. A declared component with a task, a
**contract**, an eval, a **fingerprint**, and a history. Replaces the v2 word
**node** (the manifest kind is still `Node` for format compatibility). The unit,
not the file, is what a human steers and an agent edits.

**Unit kind** — `compute` · `state` · `schema` · `config` · `external` ·
`pipeline`. What the unit *is*, by behaviour, not by file extension.

**Manifest** — `entiendo.node.yaml`: the declaration of one unit (its desired
state). The manifest *is* the retrieval index the workload reads through.

**Task** — the one-sentence statement of what a unit is for. `ent new` refuses
to scaffold a unit without one (plus a first fixture → verdict).

**Contract** — what "correct" means for *this unit alone*: input/output shape,
invariants, and `sideEffects` (`none | writes | external | irreversible`). A
neighbour sees a unit's contract, never its interior.

**Claims** — the files a unit owns; "everything that can change this behaviour."
Drives coverage and feeds the fingerprint. Exactly one unit claims a file, or it
is explicitly **unclaimed**.

**Coverage / unclaimed** — the headline number: claimed vs. unclaimed files.
Unclaimed is *visible*, not hidden — a finding ("this glue has no contract"),
not a failure.

**Boundary** — where one unit ends and the next begins. Validated by the law.

---

## Identity & change

**Fingerprint** — the composite content hash that *is* a unit's versioned
identity, over four dimensions: **code · prompt · config · model**. Replaces the
v2 word **version**. A file hash sees one dimension; the fingerprint sees all
four, so "what moved" is answerable.

**Pin** — freeze a fingerprint dimension (e.g. `ent pin <unit> model=<id>`). The
fingerprint moves; the change appears on the Timeline.

**Revert** — restore a unit to a prior fingerprint without touching anything
else (composite hash makes it unit-local).

**Replay** — run today's golden fixtures against an old fingerprint and the
current one, side by side, to attribute a delta to a specific dimension
(`ent replay <unit> --against <fingerprint>`).

---

## Verification

**Eval** — the health probe attached to a unit. Tiered by cost:

- **Reflex** (v2 **tier0**) — deterministic, <1s, runs on *every* edit
  (schema / invariant / smoke / trajectory). The AI may author these freely.
- **Golden** (v2 **tier1**) — a blessed golden dataset, runs pre-merge, scored
  with a metric against a baseline and a significance threshold.
- **Judge** (v2 **tier2**) — an expensive LLM-judge against a rubric; nightly or
  on demand. Never faked: without a wired judge it *skips*.

**Verdict** — an eval's output. Reflex: `GREEN | RED | UNTESTED | ERROR`.
Golden: `WITHIN_BAND | REGRESSED | IMPROVED | UNSTABLE | DEGRADED`.

**Health** — a unit's current verdict, judged against a **baseline** with a
**significance** threshold — never a raw score (that flickers). "Within band" is
a first-class state.

**Reconciler** — the L1 mechanism that derives *actual* edges (imports, calls,
spans, border-crossing tools) and checks them against the declared ones.
**Drift** — declared ≠ actual — is a build failure, not a warning
(`ent extract --check`). Manifests are verified, not trusted.

**Bless** — a human signing a golden dataset's expected outputs
(`humanBlessed: true`, `ent bless`). The workload may *propose* rows; only the
operator blesses. Blessing your own grader is a tautology, not a signal.

**Baseline** — the reference score a golden eval is judged against; promoted only
on human confirmation (`ent baseline accept`).

**Oracle boundary** — the verifier's own state (history, baselines, blessing
signatures, steering verdicts, the generated map, blessed golden datasets),
mechanically closed to the proposer: the claims hook denies agent writes, and
content signatures void on tamper (SPEC §17, Invariant 9).

**Oracle class** — a golden row's provenance: `contract-derivable` (the
expected value follows from the spec alone) or `implementation-derived`
(captured from the code's own output — a value that can never disagree with
it; quarantined until a human consciously accepts it at bless time).

**Effect probe** — the sandbox's audit-hook record of a unit's observed
effects (fs-write / network / subprocess). Gates one direction only: an
observed effect against `sideEffects: none` is RED; observing nothing is
graded evidence, never verification (Rice's theorem).

**Capability manifest** — a language adapter's declared blind spots,
published in `graph.json` (`adapters`); every edge carries `resolution:
complete | partial | none`. The closed-world guarantee is bounded by each
adapter's resolver, and says so.

**Second stage** — the deferred contract of the callable a factory unit
returns (`contract.secondStage` + fixture `thenCall` rows), judged per
invocation with blame: domain violations blame the caller, range violations
blame the unit (Findler–Felleisen).

---

## Agentic units

**Agentic unit** — a `compute` unit whose interior is a multi-step agent that
chooses tools. Needs more than an I/O contract: the *path* can be wrong even when
the answer is right.

**Interior** — the `interior:` manifest block: `process` (free-text description),
a `tools` registry, and `maxSteps`. The interior is private to the unit;
neighbours see only its contract.

**Tool registry** — `interior.tools`: the *only* tools the unit may call. Each
tool that crosses a border declares the edge it `crosses`, which the reconciler
verifies. `ent.guard(registry)` raises on an out-of-registry call at runtime.

**Trajectory contract** (trajectory invariant) — a reflex-tier eval over the
*sequence* of tool calls: `order` (a must precede b), `maxSteps`, `registryOnly`.
Evaluated against recorded spans or a run-log fixture. A right answer via a
forbidden order is RED.

---

## The surface

**Universe** — the render surface: one indigo field (celestial design system)
navigated with a world-coordinate camera — zoom, pan, `/`-search, keyboard nav,
minimap, group collapse. Every unit is a kind-form, health is glow, and selecting
one tints its blast radius and opens a **dossier**. Replaces the plain v2 HTML
explorer. `ent render` writes it static; `ent serve` hydrates it live.

**Lens** — one of the six views over the *same* topology: Structure · Flow ·
Trace · Health · Timeline · Blast radius. Same boxes; only colour/motion meaning
changes. The v4 lenses are live: **Trace** plays a recorded request back as a
comet (halting red on a failed hop, descending into agentic interiors),
**Timeline** is a scrubber over the real commit axis that replays fingerprints,
and a **cost overlay** shows spend against budget. Every lens ends in an action.

**Interior** — the rendered inside of an **agentic unit**: its tool registry
drawn as satellites on an orbit ring, each tethered across the border to the unit
its call crosses. The ring is solid when the registry is enforced
(`registryOnly`), dashed when not. Trace playback lights each satellite as the
agent calls it.

**Dossier** — the panel for a selected unit: task + contract + verdict +
fingerprint + edges up front, artifacts (claims) collapsed behind a disclosure.
Logic first. Ends in an action: **steer / revert / approve**.

**Blast radius** — the downstream units at risk if this one changes, ranked by
contract coupling. Turns health from reactive to preventive.

---

## The loop

**Steer** — the operator's verb: click a unit, state an intent in English. The
plane queues it (`POST /api/steer` → `entiendo/steering/queue.jsonl`); the
workload picks it up, edits within claims, and posts a verdict back to the
dossier. Steering drives the agent; the operator never types in a terminal after
session start.

**Operator skill** — the `entiendo-operator` skill that runs the workload's loop:
`await_steering` → `get_node_context` → `apply_edit` → `post_verdict`, proposing
boundary changes instead of writing around claims.

**Approval gate** — `approval.required: true`: an edit to the unit is held back as
a **proposal** rather than applied live. The dossier shows it **diff-first** — the
unified diff, the behaviour delta, and the after-verdict together — with real
Approve / Reject, and the map pulses a gold ring on any unit awaiting sign-off
(`steering.py` proposals + `/api/proposals`). Approve applies the stored diff;
Reject leaves the working tree untouched. Default `true` for `irreversible` side
effects.

**Retrofit** — the semi-automated migration of an unmanaged repo into units:
AI-proposed manifests, each phrased as a task with a candidate fixture → verdict,
accepted by the operator one unit at a time. Never a bulk scan.

---

## MCP tools (the plane's API to the workload)

`get_graph` · `get_node_context` · `run_eval` · `get_blast_radius` ·
`apply_edit` · `revert_node` · `retrofit_propose` · `retrofit_accept` ·
`validate_manifests` — and, added in v3, `await_steering` · `post_verdict` (which
can set `proposal=true` to route a gated edit into the diff-first approval flow).
The workload reads through `get_node_context` (claims + neighbour contracts only)
and writes through `apply_edit` (boundary-enforced, reflex-verified; returns the
unified diff, before/after verdict, and behaviour delta).

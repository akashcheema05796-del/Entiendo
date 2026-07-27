"""Phase A acceptance (PLAN_v3.md §A): the v3 documents are coherent.

Encodes the two mechanical acceptance criteria:
  - SPEC v3 answers "what is this" in its first ten lines (the category).
  - Every canonical v3 term used in SPEC exists in LEXICON.
Plus the basic existence of the v3 source-of-truth docs. Pure text checks —
no import of the package, so this stays green as a docs-only change.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# The canonical v3 vocabulary. Each must be DEFINED in LEXICON.md and USED in
# SPEC.md — that is the "every term used in SPEC exists in LEXICON" criterion,
# pinned to the stable core rather than to every word (which would be brittle).
CANONICAL_TERMS = [
    "control plane", "operator", "workload", "logical unit", "the law",
    "fingerprint", "reconciler", "reflex", "golden", "judge", "steer",
    "bless", "universe", "blast radius", "trajectory", "interior",
    "agentic unit",
]


def _read(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


def test_v3_docs_exist() -> None:
    for name in ("SPEC.md", "LEXICON.md", "PLAN_v3.md", "README.md"):
        assert (REPO_ROOT / name).is_file(), f"missing {name}"


def test_spec_is_v3() -> None:
    assert "Specification v3" in _read("SPEC.md")


def test_spec_names_the_category_in_first_ten_lines() -> None:
    """'what is this' answered up front — the category in the first 10 non-blank lines."""
    lines = [ln for ln in _read("SPEC.md").splitlines() if ln.strip()][:10]
    head = "\n".join(lines).lower()
    assert "control plane" in head, "SPEC must name the category in its first ten lines"


def test_every_canonical_term_is_defined_in_lexicon_and_used_in_spec() -> None:
    spec = _read("SPEC.md").lower()
    lexicon = _read("LEXICON.md").lower()
    missing_lex = [t for t in CANONICAL_TERMS if t not in lexicon]
    missing_spec = [t for t in CANONICAL_TERMS if t not in spec]
    assert not missing_lex, f"terms used but not in LEXICON: {missing_lex}"
    assert not missing_spec, f"lexicon terms not present in SPEC: {missing_spec}"


def test_the_law_is_stated_in_spec_and_lexicon() -> None:
    for name in ("SPEC.md", "LEXICON.md"):
        assert "evaluated independently on given data" in _read(name), \
            f"the law must be stated verbatim in {name}"


def test_readme_repositioned_to_control_plane() -> None:
    readme = _read("README.md")
    assert "mission control" in readme
    assert "control plane" in readme.lower()

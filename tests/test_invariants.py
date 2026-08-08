"""Restricted invariant evaluator (Phase 7 §4, §14).

Security is by allowlist: anything unrecognised is rejected, and there is no
eval()/exec() — a tree-walking interpreter runs only the permitted node types.
"""

from __future__ import annotations

import pytest

from ent.invariants import InvariantError, eval_invariant, validate_invariant


# --------------------------------------------------------------------------- #
# validation — the ACE surface must be closed
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("expr", [
    "__import__('os').system('x')",
    "output.__class__",
    "output.__class__.__bases__",
    "().__class__.__mro__",
    "output._private",
    "foo",                      # bare name that isn't input/output/builtin
    "open('x')",                # not in the builtin allowlist
    "output.chunks; input.k",   # not a single expression
    "output.items.append(1)",   # method call (Call on Attribute) is rejected
])
def test_rejects_dangerous_or_unknown(expr: str) -> None:
    with pytest.raises(InvariantError):
        validate_invariant(expr)


@pytest.mark.parametrize("expr", [
    "len(output.chunks) <= input.k",
    "all(c.score >= 0 for c in output.chunks)",
    "isinstance(output.text, str)",
    "0.0 <= output.score <= 1.0",
    "output.n == len(input.items)",
])
def test_accepts_valid_invariants(expr: str) -> None:
    validate_invariant(expr)  # must not raise


# --------------------------------------------------------------------------- #
# evaluation — dict attribute access, real values in failure detail
# --------------------------------------------------------------------------- #

def test_eval_true() -> None:
    ok, _ = eval_invariant("len(output.chunks) <= input.k", {"k": 5}, {"chunks": [1, 2]})
    assert ok


def test_eval_false_shows_real_numbers() -> None:
    ok, detail = eval_invariant("len(output.chunks) <= input.k", {"k": 1}, {"chunks": [1, 2]})
    assert not ok
    assert "len(output.chunks)=2" in detail
    assert "input.k=1" in detail


def test_eval_comprehension() -> None:
    ok, _ = eval_invariant("all(c.score >= 0 for c in output.chunks)", {},
                           {"chunks": [{"score": 1}, {"score": -1}]})
    assert not ok


def test_eval_dict_attribute_is_key_access() -> None:
    ok, _ = eval_invariant("output.a == 3", {}, {"a": 3})
    assert ok


def test_bytes_is_an_allowed_isinstance_target() -> None:
    """A codec/signer unit must be able to assert its own output type. `str`
    was allowed while `bytes` was not, which made bytes-in/bytes-out units
    unable to declare an invariant at all (found retrofitting itsdangerous)."""
    ok, _ = eval_invariant("isinstance(output, bytes)", None, b"abc")
    assert ok
    bad, _ = eval_invariant("isinstance(output, bytes)", None, "abc")
    assert not bad
    for expr, out in (("isinstance(output, bytearray)", bytearray(b"x")),
                      ("isinstance(output, frozenset)", frozenset({1}))):
        good, _ = eval_invariant(expr, None, out)
        assert good


def test_bytes_literal_membership_still_works() -> None:
    ok, _ = eval_invariant("b'=' not in output", None, b"aGVsbG8")
    assert ok
    bad, _ = eval_invariant("b'=' not in output", None, b"aGVsbG8=")
    assert not bad

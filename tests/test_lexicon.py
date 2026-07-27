"""Phase G acceptance (PLAN_v3.md §G) — the lexicon in the product.

User-facing CLI strings speak the lexicon (no bare "node"), the tiers accept
reflex / golden / judge, and the format/back-compat surface is untouched:
`entiendo.node.yaml`, `claims:`, `apiVersion: entiendo/v1`, `kind: Node`, and the
old `--node-id` / numeric `--tier` forms keep working.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent import cli  # noqa: E402
from ent.commands import eval as eval_cmd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
_WORD_NODE = re.compile(r"\bnodes?\b", re.I)


def _strip_allowed(s: str) -> str:
    # `entiendo.node.yaml` is the manifest filename — a format identifier, kept.
    return (s or "").replace("entiendo.node.yaml", "")


def test_top_description_uses_the_lexicon() -> None:
    parser = cli._build_parser()
    assert parser.description == "Entiendo — the unit is the unit of work."


def test_no_bare_node_in_user_facing_cli_strings() -> None:
    parser = cli._build_parser()
    sub = parser._subparsers._group_actions[0]
    offenders = []
    for act in sub._choices_actions:                      # subcommand short help
        if _WORD_NODE.search(_strip_allowed(act.help)):
            offenders.append(("help", act.dest, act.help))
    for name, p in sub.choices.items():                   # descriptions + arg help
        if _WORD_NODE.search(_strip_allowed(p.description or "")):
            offenders.append(("desc", name, p.description))
        for a in p._actions:
            if _WORD_NODE.search(_strip_allowed(a.help or "")):
                offenders.append(("arg", f"{name}:{a.dest}", a.help))
    assert offenders == [], f"bare 'node' in user-facing CLI strings: {offenders}"


def test_tier_lexicon_aliases_resolve() -> None:
    assert eval_cmd._TIERS["reflex"][0] == 0
    assert eval_cmd._TIERS["golden"][0] == 1
    assert eval_cmd._TIERS["judge"][0] == 2
    # numeric forms kept for back-compat
    assert eval_cmd._TIERS["0"][0] == 0 and eval_cmd._TIERS["1"][0] == 1


def test_eval_accepts_reflex_and_numeric_tiers() -> None:
    parser = cli._build_parser()
    for tier in ("reflex", "golden", "judge", "0", "1", "2"):
        ns = parser.parse_args(["eval", "x.y", "--tier", tier])
        assert ns.tier == tier


def test_node_id_flag_kept_as_alias() -> None:
    parser = cli._build_parser()
    # old --node-id and new --unit-id both land on the same dest
    assert parser.parse_args(["init", "--node-id", "a.b", "--at", "x"]).node_id == "a.b"
    assert parser.parse_args(["init", "--unit-id", "a.b", "--at", "x"]).node_id == "a.b"


def test_format_and_api_surface_unchanged() -> None:
    # The lexicon changed; the FORMAT did not (LEXICON → Compatibility).
    schema = (REPO_ROOT / "schemas" / "node.schema.json").read_text()
    assert '"const": "entiendo/v1"' in schema
    assert '"const": "Node"' in schema          # manifest kind stays Node
    assert "claims" in schema
    # the manifest filename is unchanged
    from ent.manifest import MANIFEST_FILENAME
    assert MANIFEST_FILENAME == "entiendo.node.yaml"

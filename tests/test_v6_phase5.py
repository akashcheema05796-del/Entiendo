"""PLAN_v6 Phase 5 — polish with teeth.

5.1 secret values never enter the config hash (a rotated secret is not a
    behaviour change; renaming the KEY still is).
5.2/5.3 CRLF → LF normalisation for prompt/config hashing — a Windows checkout
    doesn't mint a phantom version.
5.4 measured-budget label honesty: a tiny sample's "p95" is labeled as the max
    it actually is.
5.6 the trace-capture composite failure is no longer silent (stderr warning).
5.7 / 5.10 the canvas carries the particle cap + offscreen skip, and a legacy
    blessedBy "unknown" renders as an unverified historical blessing.
(5.5 is the behavioural rewrite of the bless bypass test in
 tests/test_v3_blessedby.py; 5.9 is MOOTED by 4.2 — see docs/V6_VERIFICATION.md.)
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent.render import _measured_budgets  # noqa: E402
from ent.manifest import Node, load  # noqa: E402
from ent.version import compute_version  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = (REPO_ROOT / "src/ent/universe.html").read_text()


def _node(tmp_path: Path, files: dict[str, str]) -> Node:
    claims = "\n".join(f"  - {rel}" for rel in files)
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, newline="")            # write EXACTLY as given
    manifest = tmp_path / "entiendo.node.yaml"
    manifest.write_text(
        f"apiVersion: entiendo/v1\nkind: Node\nid: demo.node\nname: demo\n"
        f"nodeKind: compute\nowner: me\nclaims:\n{claims}\n"
        "contract:\n  sideEffects: none\n")
    return Node.from_manifest(load(manifest), manifest)


# --------------------------------------------------------------------------- #
# 5.1 secrets never enter the config hash
# --------------------------------------------------------------------------- #

def test_rotated_secret_does_not_move_the_composite(tmp_path: Path) -> None:
    node = _node(tmp_path, {"app.yaml": "api_key: AAAA\nretries: 3\n"})
    v1 = compute_version(node, tmp_path)
    (tmp_path / "app.yaml").write_text("api_key: BBBB\nretries: 3\n")
    v2 = compute_version(node, tmp_path)
    assert v1["composite"] == v2["composite"]        # rotation is not behaviour


def test_secret_key_rename_and_real_config_changes_still_move_it(tmp_path: Path) -> None:
    node = _node(tmp_path, {"app.yaml": "api_key: AAAA\nretries: 3\n"})
    v1 = compute_version(node, tmp_path)
    (tmp_path / "app.yaml").write_text("api_key: AAAA\nretries: 5\n")
    assert compute_version(node, tmp_path)["composite"] != v1["composite"]
    (tmp_path / "app.yaml").write_text("service_api_key: AAAA\nretries: 3\n")
    assert compute_version(node, tmp_path)["composite"] != v1["composite"]


def test_secret_values_appear_nowhere_in_the_version(tmp_path: Path) -> None:
    node = _node(tmp_path, {"app.yaml": "password: hunter2\n"})
    v = compute_version(node, tmp_path)
    assert "hunter2" not in str(v)                   # reference-only (Invariant 6)


# --------------------------------------------------------------------------- #
# 5.2 / 5.3 line-ending normalisation
# --------------------------------------------------------------------------- #

def test_crlf_prompt_and_config_hash_like_lf(tmp_path: Path) -> None:
    lf = _node(tmp_path / "a", {"p.md": "You are a bot.\nBe kind.\n",
                                "c.yaml": "retries: 3\n"})
    crlf = _node(tmp_path / "b", {"p.md": "You are a bot.\r\nBe kind.\r\n",
                                  "c.yaml": "retries: 3\r\n"})
    va, vb = compute_version(lf, tmp_path / "a"), compute_version(crlf, tmp_path / "b")
    assert va["prompt"] == vb["prompt"]
    assert va["config"] == vb["config"]
    assert va["composite"] == vb["composite"]        # no phantom Windows version


# --------------------------------------------------------------------------- #
# 5.4 budget label honesty
# --------------------------------------------------------------------------- #

def _traces(n: int) -> list[dict]:
    return [{"hops": [{"node": "u", "duration_ms": float(i + 1), "cost_usd": 0.0}]}
            for i in range(n)]


def test_small_windows_are_labeled_max_not_p95() -> None:
    small = _measured_budgets(_traces(3))["u"]
    assert small["p95Basis"] == "max of 3"
    big = _measured_budgets(_traces(25))["u"]
    assert big["p95Basis"] == "p95"
    assert "p95Basis" in UNIVERSE                    # …and the dossier uses it


# --------------------------------------------------------------------------- #
# 5.6 the trace-capture composite failure is loud
# --------------------------------------------------------------------------- #

def test_composite_failure_during_capture_warns_on_stderr(tmp_path: Path, capsys) -> None:
    from ent.history import _composites_for
    (tmp_path / "entiendo.node.yaml").write_text("id: [broken\n")    # malformed
    out = _composites_for(tmp_path, {"ghost.node"})
    assert out == {"ghost.node": None}               # still degrades, never raises
    err = capsys.readouterr().err
    assert "warning" in err and "ghost.node" in err  # …but no longer silently


# --------------------------------------------------------------------------- #
# 5.7 / 5.10 canvas honesty
# --------------------------------------------------------------------------- #

def test_particles_cap_on_dense_maps_and_skip_offscreen() -> None:
    assert "units.length > 100" in UNIVERSE          # density cap
    assert "x<x0||x>x1||y<y0||y>y1" in UNIVERSE      # offscreen skip


def test_legacy_unknown_blessing_renders_as_unverified() -> None:
    assert "unverified historical blessing" in UNIVERSE

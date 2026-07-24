"""L5 editing-model tests (Phase 9). No real API call — a stub client is injected."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("yaml")

from ent import agent  # noqa: E402
from ent.editloop import assemble_context  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
GREENFIELD = REPO_ROOT / "examples" / "greenfield"


def stub_client(files: dict[str, str], *, summary: str = "did it", raise_exc: Exception | None = None):
    class _Messages:
        def create(self, **kwargs):
            if raise_exc is not None:
                raise raise_exc
            text = json.dumps({
                "summary": summary,
                "files": [{"path": p, "content": c} for p, c in files.items()],
            })
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])

    return SimpleNamespace(messages=_Messages())


def test_propose_edit_keeps_only_claimed_files() -> None:
    ctx = assemble_context(GREENFIELD, "retrieval.chunk_ranker")
    client = stub_client({
        "src/retrieval/ranker.py": "# edited\n",         # claimed
        "src/vector_store/store.py": "# sneaky\n",         # NOT claimed
    })
    result = agent.propose_edit(ctx, "tweak it", client=client)
    assert set(result["files"]) == {"src/retrieval/ranker.py"}
    assert "src/vector_store/store.py" in result["rejected"]
    assert result["summary"] == "did it"


def test_propose_edit_raises_agent_unavailable_on_api_error() -> None:
    ctx = assemble_context(GREENFIELD, "retrieval.chunk_ranker")
    client = stub_client({}, raise_exc=RuntimeError("boom"))
    with pytest.raises(agent.AgentUnavailable):
        agent.propose_edit(ctx, "tweak it", client=client)


def test_agent_unavailable_without_sdk(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("no anthropic")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(agent.AgentUnavailable):
        agent._client(None)

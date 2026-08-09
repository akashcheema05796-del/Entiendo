"""MCP Registry readiness (research rec F, part 1).

server.json is prepared so that the day `entiendo` lands on PyPI, publishing
to the official MCP Registry is one `mcp-publisher publish`. These tests keep
the prepared artifacts from drifting apart in the meantime — the registry
validates all of this on publish day, but publish day is the wrong time to
find out.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER = json.loads((REPO_ROOT / "server.json").read_text())


def _pyproject_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text()
    return re.search(r'^version = "([^"]+)"', text, re.M).group(1)


def test_versions_agree_everywhere() -> None:
    """pyproject, server.json top-level, and the package entry must match —
    the registry rejects mismatches, and a stale server.json after a release
    bump would publish the wrong thing."""
    v = _pyproject_version()
    assert SERVER["version"] == v
    assert SERVER["packages"][0]["version"] == v


def test_namespace_matches_github_authentication() -> None:
    """GitHub-authenticated publishers must use io.github.<username>/ — and
    the username must be the repo owner or login fails on publish day."""
    assert SERVER["name"] == "io.github.akashdatageek/entiendo"
    assert SERVER["repository"]["url"].startswith(
        "https://github.com/akashdatageek/")


def test_readme_carries_the_pypi_ownership_marker() -> None:
    """PyPI ownership is verified by an mcp-name line in the package README
    (HTML comment form). pyproject points readme at README.md, so the marker
    must live there and name the same server."""
    readme = (REPO_ROOT / "README.md").read_text()
    assert f"mcp-name: {SERVER['name']}" in readme


def test_the_package_runs_through_uvx() -> None:
    """`uvx <package>` executes the console script named after the package —
    so the alias `entiendo` must exist alongside `ent`, and the package entry
    must be stdio via uvx with the [mcp] extra (the server's deps live there)."""
    pkg = SERVER["packages"][0]
    assert pkg["registryType"] == "pypi"
    assert pkg["identifier"] == "entiendo"
    assert pkg["runtimeHint"] == "uvx"
    assert pkg["transport"]["type"] == "stdio"
    args = {a.get("value") for a in pkg.get("runtimeArguments", [])}
    assert "entiendo[mcp]" in args
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()
    assert 'entiendo = "ent.cli:main"' in pyproject

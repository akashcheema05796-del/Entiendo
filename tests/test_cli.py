"""CLI-surface guards."""

from __future__ import annotations

from pathlib import Path


def test_version_matches_pyproject() -> None:
    """One source of truth. A hardcoded __version__ silently drifted to 0.1.0
    while the package shipped 0.2.0 — caught only by installing the built wheel
    in a clean room. Now derived from distribution metadata; this guards the
    fallback path and the pyproject value agreeing."""
    import re
    import ent
    root = Path(__file__).resolve().parents[1]
    declared = re.search(r'^version\s*=\s*"([^"]+)"',
                         (root / "pyproject.toml").read_text(), re.M).group(1)
    assert ent.__version__ == declared, (
        f"ent.__version__={ent.__version__} but pyproject says {declared} — "
        "reinstall (pip install -e .) or fix the version")
    assert ent.__version__ != "0+unknown"

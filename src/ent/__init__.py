"""Entiendo — the node is the unit of work.

Build-time instrumentation, a generated system map, and a scoped editing loop.
See SPEC.md for the full specification.

Public surface:
    ent.node     — the @ent.node("<id>") instrumentation decorator (L2)
    ent.record   — meter cost / tokens onto the current node's span (L2)

Everything else is internal and moves as the phases land (L0 → L5).
"""

from __future__ import annotations

from pathlib import Path

# Single source of truth is pyproject.toml — read it back from the installed
# distribution metadata rather than restating it here. A hardcoded copy silently
# drifted (the package said 0.2.0 while `ent --version` said 0.1.0, caught by a
# clean-room install of the wheel). The fallback covers running from a source
# checkout that was never installed.
def _resolve_version() -> str:
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("entiendo")
    except PackageNotFoundError:
        pass
    import re
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(), re.M)
    except OSError:
        return "0+unknown"
    return m.group(1) if m else "0+unknown"


__version__ = _resolve_version()
__api_version__ = "entiendo/v1"

from .instrument import guard, node, record

__all__ = ["node", "record", "guard", "__version__", "__api_version__"]

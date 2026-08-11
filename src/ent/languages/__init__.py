"""The language registry — pick an extractor by file extension.

The reconciler calls `for_file(path)` and, if it gets an extractor, asks it for
the file's intra-project imports. Registering a language here is the whole
integration surface; the reconciler itself is language-neutral.
"""

from __future__ import annotations

from pathlib import Path

from .base import AdapterCapabilities, ImportEdge, LanguageExtractor
from .python import PythonExtractor
from .typescript import TypeScriptExtractor

__all__ = ["AdapterCapabilities", "ImportEdge", "LanguageExtractor",
           "for_file", "extensions", "register", "registered"]

_REGISTRY: list[LanguageExtractor] = []


def register(extractor: LanguageExtractor) -> None:
    """Add a language extractor (later registrations win on extension clash)."""
    _REGISTRY.insert(0, extractor)


def for_file(file: Path) -> LanguageExtractor | None:
    """The extractor that handles `file`'s extension, or None."""
    suffix = Path(file).suffix
    for extractor in _REGISTRY:
        if suffix in extractor.extensions:
            return extractor
    return None


def extensions() -> frozenset[str]:
    """Every extension any registered extractor handles."""
    return frozenset(e for ex in _REGISTRY for e in ex.extensions)


def registered() -> list[LanguageExtractor]:
    """Every registered extractor — the graph publishes their capability
    manifests so the closed-world guarantee's holes are declared, not hidden."""
    return list(_REGISTRY)


# Built-ins. Python first so it wins any (currently non-existent) clash.
register(TypeScriptExtractor())
register(PythonExtractor())

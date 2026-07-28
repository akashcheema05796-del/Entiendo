"""The language-agnostic extractor seam (L1).

The reconciler needs exactly one language-specific fact about a source file:
**which other files in the project does it import?** Everything downstream —
mapping a file to its owning unit, deriving unit→unit edges, reconciling those
against the declared `dependencies`, failing on drift — is language-neutral.

So that one step is the seam. A `LanguageExtractor` encapsulates *parse +
resolve* for one language and returns resolved, intra-project import targets; the
registry (`languages/__init__.py`) picks an extractor by file extension. Adding a
language is adding an extractor, not touching the reconciler.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ImportEdge:
    """One resolved intra-project import.

    `target` is the imported file (absolute, inside the project). `detail` is the
    raw specifier as written, used verbatim as edge evidence
    (`"<claim> imports <detail>"`) so the graph reads the same across languages.
    """

    target: Path
    detail: str


@runtime_checkable
class LanguageExtractor(Protocol):
    """Parse + resolve the imports of one language."""

    name: str
    extensions: tuple[str, ...]

    def resolved_imports(self, file: Path, root: Path) -> list[ImportEdge]:
        """Every intra-project file `file` imports.

        External/third-party imports and anything that doesn't resolve to a file
        inside `root` are omitted — the reconciler only reasons about edges
        between the project's own units.
        """
        ...

"""Shared helper for not-yet-implemented commands.

The scaffold ships every command in the CLI surface, but only L0 carries real
logic. Later commands print exactly which phase implements them and exit
non-zero, so nothing silently pretends to succeed.
"""

from __future__ import annotations

import textwrap

# Standard non-zero exit for "wired, but this phase isn't built yet".
EXIT_NOT_IMPLEMENTED = 3


def not_implemented(*, command: str, phase: str, summary: str, acceptance: str) -> int:
    """Print a phase-anchored stub message and return the standard exit code."""
    message = textwrap.dedent(
        f"""\
        ent {command}: not implemented yet — planned for {phase}.

          {summary}

          Acceptance (SPEC.md §8): {acceptance}

        Build L0 → L5 in strict order. See SPEC.md and docs/build-order.md.
        """
    )
    print(message, end="")
    return EXIT_NOT_IMPLEMENTED

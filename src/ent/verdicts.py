"""Verdict vocabulary for evals (Phase 7 §5, §7, §9).

tier0 yields one of four states; tier1 adds the statistical / budget outcomes.
Everything maps to a health colour (render surface) and a CLI exit code (CI).
Centralised here so the runner, CLI, and render surface never disagree.
"""

from __future__ import annotations

# tier0
GREEN = "GREEN"          # executed, all checks passed
RED = "RED"              # executed, a check failed
UNTESTED = "UNTESTED"    # no entrypoint, or executionMode: skip
ERROR = "ERROR"          # harness failure — import error, I/O violation
ENV_BLOCKED = "ENV-BLOCKED"  # contract.requires names a runtime absent HERE —
                             # the judge is in the wrong room, the unit is not
                             # broken (astrobee: rosbag/tf outside a ROS install)

# tier1 (statistical / budget)
WITHIN_BAND = "WITHIN_BAND"
REGRESSED = "REGRESSED"
IMPROVED = "IMPROVED"
UNSTABLE = "UNSTABLE"
DEGRADED = "DEGRADED"

ALL = (GREEN, RED, UNTESTED, ERROR, ENV_BLOCKED,
       WITHIN_BAND, REGRESSED, IMPROVED, UNSTABLE, DEGRADED)

# Health lens colour (SPEC §4 / Phase 7 §5).
#   green  — healthy / within band / improved
#   red    — failed / regressed
#   grey   — untested (hatched)
#   amber  — harness error, unstable, or over-budget
HEALTH_COLOUR = {
    GREEN: "green", WITHIN_BAND: "green", IMPROVED: "green",
    RED: "red", REGRESSED: "red",
    UNTESTED: "grey", ENV_BLOCKED: "grey",
    ERROR: "amber", UNSTABLE: "amber", DEGRADED: "amber",
}

# CLI exit codes (Phase 7 §11).
#   0 pass/within-band · 1 red/regressed · 2 error · 4 unstable/degraded
# UNTESTED is not a failure → 0 (but it is counted and rendered grey).
EXIT_CODE = {
    GREEN: 0, WITHIN_BAND: 0, IMPROVED: 0, UNTESTED: 0, ENV_BLOCKED: 0,
    RED: 1, REGRESSED: 1,
    ERROR: 2,
    UNSTABLE: 4, DEGRADED: 4,
}


def colour(verdict: str) -> str:
    return HEALTH_COLOUR.get(verdict, "amber")


def exit_code(verdict: str) -> int:
    return EXIT_CODE.get(verdict, 2)

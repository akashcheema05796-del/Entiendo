"""Component-property detectors (hardening plan, Phase 3).

Detectors report *properties* of a unit — `time_pure: true/false` with
evidence — never test failures. A unit that reads the clock isn't wrong;
a unit that reads the clock *silently* is a landmine under every golden
captured today.
"""

"""L0 — Manifest validation.

Two layers of checking, in order:

1. **Schema** — every manifest conforms to schemas/node.schema.json.
2. **Semantics** — rules the JSON-Schema can't express on its own:
     - node ids are globally unique
     - contract input/output `$ref` targets resolve to real files
     - claimed files exist (Invariant 4 — a claim on a missing file is wrong)
     - tier1 golden datasets are `humanBlessed: true` (SPEC.md §5.2)

Failures are collected, not raised on first sight, so `ent validate` can report
everything wrong in one pass — fast and specific (SPEC.md §10).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .manifest import MANIFEST_FILENAME, discover, load
from .schema import build_validator


@dataclass
class FileResult:
    """Validation outcome for a single manifest."""

    path: Path
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class Report:
    """Aggregate validation outcome across a set of manifests."""

    results: list[FileResult] = field(default_factory=list)
    # Errors not tied to a single file (e.g. duplicate ids across two files).
    cross_errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.cross_errors and all(r.ok for r in self.results)

    @property
    def error_count(self) -> int:
        return len(self.cross_errors) + sum(len(r.errors) for r in self.results)


def validate_paths(paths: list[Path], *, root: Path) -> Report:
    """Validate a specific set of manifest files.

    `root` is the project root that claim paths are resolved against.
    """
    validator = build_validator()
    report = Report()

    # id -> first path that declared it, for uniqueness checking.
    seen_ids: dict[str, Path] = {}

    for path in paths:
        result = FileResult(path=path)
        report.results.append(result)

        try:
            manifest = load(path)
        except Exception as exc:  # YAML / not-a-mapping / missing file
            result.errors.append(f"could not parse: {exc}")
            continue

        # --- 1. schema conformance ---
        schema_errors = sorted(
            validator.iter_errors(manifest),
            key=lambda e: list(e.path),
        )
        for err in schema_errors:
            location = "/".join(str(p) for p in err.path) or "<root>"
            result.errors.append(f"schema: {location}: {err.message}")

        # If the doc doesn't even match the schema, semantic checks below would
        # just produce noise. Report schema errors alone and move on.
        if schema_errors:
            continue

        # --- 2. semantic checks ---
        _check_id_uniqueness(manifest, path, seen_ids, report)
        _check_ref_targets(manifest, path, result)
        _check_claims_exist(manifest, root, result)
        _check_human_blessed(manifest, result)

    return report


def validate_root(root: Path) -> Report:
    """Discover and validate every manifest under `root`."""
    root = Path(root)
    paths = discover(root)
    report = validate_paths(paths, root=root)
    if not paths:
        report.cross_errors.append(
            f"no {MANIFEST_FILENAME} files found under {root}"
        )
    return report


# --------------------------------------------------------------------------- #
# semantic checks
# --------------------------------------------------------------------------- #

def _check_id_uniqueness(
    manifest: dict[str, Any],
    path: Path,
    seen_ids: dict[str, Path],
    report: Report,
) -> None:
    node_id = manifest["id"]
    if node_id in seen_ids:
        report.cross_errors.append(
            f"duplicate node id '{node_id}': {seen_ids[node_id]} and {path}"
        )
    else:
        seen_ids[node_id] = path


def _check_ref_targets(manifest: dict[str, Any], path: Path, result: FileResult) -> None:
    contract = manifest.get("contract", {})
    for side in ("input", "output"):
        spec = contract.get(side)
        if isinstance(spec, dict) and "$ref" in spec:
            ref = spec["$ref"]
            target = (path.parent / ref).resolve()
            if not target.exists():
                result.errors.append(
                    f"contract.{side}.$ref: '{ref}' does not resolve to a file"
                )


def _check_claims_exist(manifest: dict[str, Any], root: Path, result: FileResult) -> None:
    for claim in manifest.get("claims", []):
        if not (root / claim).exists():
            result.errors.append(f"claims: '{claim}' does not exist under {root}")


def _check_human_blessed(manifest: dict[str, Any], result: FileResult) -> None:
    for i, golden in enumerate(manifest.get("evals", {}).get("tier1", [])):
        if golden.get("type") == "golden" and golden.get("humanBlessed") is not True:
            result.errors.append(
                f"evals.tier1[{i}]: golden datasets require humanBlessed: true "
                "(SPEC.md §5.2 — the AI may propose rows, not bless them)"
            )

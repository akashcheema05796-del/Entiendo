"""L0 — Node schema loading.

Single source of truth for the bundled JSON-Schema (schemas/node.schema.json).
Both the validator and the tests load through here so they can never disagree.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .manifest import schema_path


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """Load and cache the node JSON-Schema."""
    return json.loads(schema_path().read_text())


def build_validator() -> Any:
    """Return a Draft 2020-12 validator for the node schema.

    Raises:
        ModuleNotFoundError: if `jsonschema` is not installed.
        jsonschema.exceptions.SchemaError: if the schema itself is malformed.
    """
    import jsonschema  # local import: keeps the dependency lazy

    schema = load_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)

# server/app/db/openapi_money.py
"""OpenAPI fix for money request fields (Session 115, Waiting item 112).

`MoneyIn` (money.py) rounds before the range checks run, so pydantic cannot push the
use-site `Field(ge=, le=)` into the float and prints them as raw `ge` / `le` keys in the
schema. Those are not JSON Schema. This renames them to the standard keys, as floats
(what pydantic wrote for float fields before `MoneyIn`). It only renames; it never
changes validation, and running it twice changes nothing.
"""
from typing import Any

_RENAMES = {
    "ge": "minimum",
    "le": "maximum",
    "gt": "exclusiveMinimum",
    "lt": "exclusiveMaximum",
}


def _fix(node: Any) -> None:
    if isinstance(node, dict):
        for old, new in _RENAMES.items():
            value = node.get(old)
            # Only a plain number is a leaked constraint; a property called "ge" holds a dict.
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                del node[old]
                node.setdefault(new, float(value))
        for child in node.values():
            _fix(child)
    elif isinstance(node, list):
        for child in node:
            _fix(child)


def normalize_money_schema(spec: dict) -> dict:
    """Fix the leaked keys inside the component schemas and operations of `spec`."""
    _fix(spec.get("components", {}).get("schemas", {}))
    _fix(spec.get("paths", {}))
    return spec
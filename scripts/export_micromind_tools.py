# scripts/export_micromind_tools.py
"""
Builds the AI tool manifest: the operations MicroMind may ask the server to run.

Reads shared-schema/openapi.json (the real contract) and an allowlist, then writes
two files with the same content:
  - shared-schema/micromind_tools.yaml   (for people and for MicroMind configuration)
  - shared-schema/micromind_tools.json   (read by server/app/services/ai_tools.py)

- Only operations in ALLOWED_READS are emitted. If one is missing from the contract,
  the script fails and lists it (fix the allowlist or the route, never invent an entry).
- Only path and query parameters are emitted. Header and cookie parameters (the
  Authorization header) never reach the model.
- A parameter that names an identity (pharmacy_id, user_id, token, role, scope...)
  is never emitted; if the contract makes one required the script fails.
- No third-party YAML package needed: JSON scalars are valid YAML.

Usage (project root):
    python scripts/export_micromind_tools.py            # write both files
    python scripts/export_micromind_tools.py --check    # fail if either file is stale
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPENAPI = ROOT / "shared-schema" / "openapi.json"
OUT_YAML = ROOT / "shared-schema" / "micromind_tools.yaml"
OUT_JSON = ROOT / "shared-schema" / "micromind_tools.json"

# (method, path) -> (tool name, scope that must already be held by the signed-in user)
# Scope names are the real ones from ROLE_PERMISSIONS. The server still enforces
# them on the endpoint itself; this column is documentation for the router.
# None means no scope: /api/me/activity only needs a signed-in user with a selected
# pharmacy and returns that user's own totals (read from me.py, Session 54).
ALLOWED_READS = {
    ("get", "/api/inventory/items"): ("search_inventory", "view_inventory"),
    ("post", "/api/inventory/match"): ("match_product", "view_inventory"),
    ("get", "/api/inventory/items/{item_id}/batches"): ("get_item_batches", "view_inventory"),
    ("get", "/api/ledger/entries"): ("list_ledger_entries", "view_reports"),
    ("get", "/api/ledger/payables"): ("list_supplier_payables", "view_reports"),
    ("get", "/api/ledger/payables/summary"): ("get_payables_summary", "view_reports"),
    ("get", "/api/me/activity"): ("get_my_activity", None),
}

# Actions the AI may only PROPOSE. They run in the local LangGraph pipeline
# (agents/), are stored as PendingAction rows, and only a human confirm writes data.
PROPOSAL_INTENTS = {
    "log_sale": "Propose a sale. Stock and price are checked locally.",
    "log_restock": "Propose a restock of an existing product.",
    "log_expense": "Propose an expense entry.",
}

# Never exposed as tools, whatever the AI asks.
FORBIDDEN_PATH_PREFIXES = [
    "/api/auth",
    "/api/pharmacies",
    "/api/staff",
    "/api/ocr",
    "/api/actions",           # confirm and cancel are human-only
    "/api/ledger/entries/{entry_id}/settlements",  # paying a supplier is human-only
]

# Argument names the model may never supply: identity always comes from the token.
DENIED_ARGUMENT_NAMES = [
    "pharmacy_id", "user_id", "token", "authorization", "role", "scope", "scopes",
    "confirmed", "created_by", "confirmed_by",
]

# Keys removed from every tool result before text goes back to MicroMind. The
# executor also drops any key that contains "profit" and scrubs phone-like numbers,
# IDs and emails from every string. "notes" is free text typed by staff and can
# hold a customer name or number, so it is never returned.
NEVER_RETURN_KEYS = [
    "phone", "pin", "token", "password", "email", "birth_date", "photo",
    "confirmed_by_name", "created_by", "paid_by", "user_id",
    "unit_buy_price", "unit_cost", "profit", "gross_profit", "notes",
]

MAX_TOOL_CALLS_PER_MESSAGE = 3

_SCHEMA_KEYS = ("minimum", "maximum", "maxLength", "enum", "default")


def resolve(spec, schema):
    """Follow a local $ref and unwrap Optional (anyOf with null)."""
    while isinstance(schema, dict):
        if "$ref" in schema:
            node = spec
            for part in schema["$ref"].lstrip("#/").split("/"):
                node = node[part]
            schema = node
            continue
        options = [s for s in schema.get("anyOf", []) if s.get("type") != "null"]
        if options and "type" not in schema:
            schema = options[0]
            continue
        break
    return schema if isinstance(schema, dict) else {}


def field_info(spec, schema):
    schema = resolve(spec, schema)
    info = {"type": schema.get("type", "string")}
    for key in _SCHEMA_KEYS:
        if key in schema:
            info[key] = schema[key]
    return info


def build_tool(spec, method, path, name, scope):
    op = spec["paths"][path][method]
    raw_params = list(spec["paths"][path].get("parameters", [])) + list(op.get("parameters", []))
    parameters = []
    for p in raw_params:
        if p["in"] not in ("path", "query"):
            continue  # header and cookie parameters never reach the model
        if p["name"] in DENIED_ARGUMENT_NAMES:
            if p.get("required"):
                raise SystemExit(f"{method.upper()} {path} requires '{p['name']}', which the model may not supply")
            continue
        entry = {"name": p["name"], "in": p["in"], "required": bool(p.get("required", False))}
        entry.update(field_info(spec, p.get("schema", {})))
        parameters.append(entry)

    tool = {
        "name": name,
        "kind": "read",
        "method": method.upper(),
        "path": path,
        "requires_scope": scope,
        "summary": op.get("summary", ""),
        "parameters": parameters,
    }

    body = op.get("requestBody")
    if body:
        schema = resolve(spec, body.get("content", {}).get("application/json", {}).get("schema", {}))
        props = {}
        for prop_name, prop_schema in schema.get("properties", {}).items():
            if prop_name in DENIED_ARGUMENT_NAMES:
                continue
            props[prop_name] = field_info(spec, prop_schema)
        required = [r for r in schema.get("required", []) if r in props]
        tool["body"] = {"properties": props, "required": required}
    return tool


def build_manifest():
    spec = json.loads(OPENAPI.read_text(encoding="utf-8"))
    paths = spec.get("paths", {})
    missing = [k for k in ALLOWED_READS if k[1] not in paths or k[0] not in paths[k[1]]]
    if missing:
        raise SystemExit(
            "Allowlisted operations not in shared-schema/openapi.json:\n"
            + "\n".join(f"  {m.upper()} {p}" for m, p in missing)
        )
    return {
        "version": 1,
        "execution": {
            "where": "roshetta-server",
            "identity": "the signed-in user token of the chat request; the model never sees or sends a token",
            "isolation": "pharmacy_id comes from the token, never from model arguments",
            "model_returns": "tool name plus arguments only",
            "results_to_model": "minimum text needed; keys in never_return_keys removed",
            "max_tool_calls_per_message": MAX_TOOL_CALLS_PER_MESSAGE,
        },
        "never_return_keys": NEVER_RETURN_KEYS,
        "denied_argument_names": DENIED_ARGUMENT_NAMES,
        "tools": [
            build_tool(spec, method, path, name, scope)
            for (method, path), (name, scope) in ALLOWED_READS.items()
        ],
        "proposals": [
            {
                "intent": intent,
                "kind": "proposal_only",
                "runs": "local agents pipeline (agents/), not an HTTP tool",
                "description": text,
                "confirmation": "human confirms in the app; only then data changes",
            }
            for intent, text in PROPOSAL_INTENTS.items()
        ],
        "forbidden_path_prefixes": FORBIDDEN_PATH_PREFIXES,
    }


# ---- tiny YAML writer (JSON scalars are valid YAML) ----

_BARE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESERVED = {"y", "n", "yes", "no", "on", "off", "null", "true", "false"}


def q(value):
    return json.dumps(value, ensure_ascii=False)


def key_text(key):
    return key if _BARE_KEY.match(key) and key.lower() not in _RESERVED else q(key)


def is_container(value):
    return isinstance(value, (dict, list)) and len(value) > 0


def emit_dict(data):
    lines = []
    for key, value in data.items():
        if is_container(value):
            lines.append(f"{key_text(key)}:")
            lines += ["  " + l for l in emit_value(value)]
        else:
            lines.append(f"{key_text(key)}: {q(value)}")
    return lines


def emit_value(value):
    if isinstance(value, dict):
        return emit_dict(value)
    lines = []
    for item in value:
        if isinstance(item, dict) and item:
            inner = emit_dict(item)
            lines.append("- " + inner[0])
            lines += ["  " + l for l in inner[1:]]
        else:
            lines.append(f"- {q(item)}")
    return lines


def render():
    manifest = build_manifest()
    header = "# shared-schema/micromind_tools.yaml  (GENERATED by scripts/export_micromind_tools.py, do not edit)\n"
    yaml_text = header + "\n".join(emit_dict(manifest)) + "\n"
    json_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    return yaml_text, json_text


def main():
    yaml_text, json_text = render()
    if "--check" in sys.argv:
        for path, text in ((OUT_YAML, yaml_text), (OUT_JSON, json_text)):
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                raise SystemExit(f"{path.name} is stale; run scripts/export_micromind_tools.py")
        print("micromind_tools.yaml and micromind_tools.json are up to date")
        return
    OUT_YAML.write_text(yaml_text, encoding="utf-8")
    OUT_JSON.write_text(json_text, encoding="utf-8")
    print(f"wrote {OUT_YAML} and {OUT_JSON}")


if __name__ == "__main__":
    main()
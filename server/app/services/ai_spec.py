# server/app/services/ai_spec.py
"""Turns the FastAPI-generated spec of the /ai app into the spec MicroMind's OpenAPI Toolkit reads.

FastAPI's raw output has things a simple toolkit parser (or a model) should not meet:
- the Authorization header appears as an ordinary optional parameter of every operation,
  which a toolkit may offer to the model as an argument it can fill;
- `$ref` pointers into `components`, `anyOf` with `null` for every Optional field, and
  validation-error response schemas.

This module removes header parameters (authentication is declared once as a bearer
scheme instead), inlines `$ref`, collapses `anyOf` with `null`, drops titles and response
schemas. It imports nothing from FastAPI so it can be tested on its own.
"""

from typing import Any

# Argument names the model may never supply. A path or query parameter with one of these
# names is a bug in the AI app, so the build fails instead of dropping it silently.
DENIED_ARGUMENT_NAMES = {
    "pharmacy_id", "user_id", "token", "authorization", "role", "scope", "scopes",
    "confirmed", "created_by", "confirmed_by",
}

_MAX_REF_DEPTH = 8

# The toolkit checks the arguments of every POST tool against a schema whose only required
# property is `RequestBody` (an object holding the JSON body). Models often send the body
# fields at the top level and the call fails before it reaches the server (Session 127), so the
# rule is stated where the model reads the tool: in the summary and the request-body text.
REQUEST_BODY_HINT = "Send the fields inside one object named RequestBody."


def _deref(node: Any, components: dict, depth: int = 0) -> Any:
    if depth > _MAX_REF_DEPTH:
        raise ValueError("Schema nesting or recursion is too deep for the AI spec.")
    if isinstance(node, list):
        return [_deref(item, components, depth) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        if name not in components:
            raise ValueError(f"Unknown schema reference: {node['$ref']}")
        return _deref(components[name], components, depth + 1)
    return {key: _deref(value, components, depth) for key, value in node.items()}


def _simplify(schema: Any) -> Any:
    if isinstance(schema, list):
        return [_simplify(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    if "anyOf" in schema:
        options = [o for o in schema["anyOf"] if not (isinstance(o, dict) and o.get("type") == "null")]
        if len(options) == 1:
            rest = {k: v for k, v in schema.items() if k != "anyOf"}
            return _simplify({**rest, **options[0]})
    result = {}
    for key, value in schema.items():
        if key == "title":
            continue
        if key == "properties" and isinstance(value, dict):
            result[key] = {name: _simplify(sub) for name, sub in value.items()}
        elif key in ("items", "anyOf", "oneOf", "allOf"):
            result[key] = _simplify(value)
        else:
            result[key] = value
    return result


def toolkit_spec(raw: dict) -> dict:
    """Return the cleaned spec. Raises ValueError if an operation lacks an operationId or
    exposes an identity-named argument."""
    components = raw.get("components", {}).get("schemas", {})
    paths: dict = {}
    for path, methods in raw.get("paths", {}).items():
        for method, operation in methods.items():
            if method.lower() not in {"get", "post"}:
                continue
            operation_id = operation.get("operationId")
            if not operation_id:
                raise ValueError(f"{method.upper()} {path} has no operationId.")
            parameters = []
            for parameter in operation.get("parameters", []):
                if parameter.get("in") not in ("path", "query"):
                    continue  # header and cookie parameters never reach the model
                if parameter["name"].lower() in DENIED_ARGUMENT_NAMES:
                    raise ValueError(f"{method.upper()} {path} exposes the argument '{parameter['name']}'.")
                entry = {
                    "name": parameter["name"],
                    "in": parameter["in"],
                    "required": bool(parameter.get("required", False)),
                    "schema": _simplify(_deref(parameter.get("schema", {}), components)),
                }
                if parameter.get("description"):
                    entry["description"] = parameter["description"]
                parameters.append(entry)
            cleaned = {
                "operationId": operation_id,
                "summary": operation.get("summary", ""),
            }
            if parameters:
                cleaned["parameters"] = parameters
            body = operation.get("requestBody")
            if body:
                schema = body.get("content", {}).get("application/json", {}).get("schema", {})
                schema = _simplify(_deref(schema, components))
                for name in schema.get("properties", {}):
                    if name.lower() in DENIED_ARGUMENT_NAMES:
                        raise ValueError(f"{method.upper()} {path} body exposes '{name}'.")
                summary = str(cleaned["summary"]).rstrip()
                if summary and summary[-1] not in ".!?":
                    summary += "."
                cleaned["summary"] = (summary + " " + REQUEST_BODY_HINT).strip()
                cleaned["requestBody"] = {
                    "description": REQUEST_BODY_HINT,
                    "required": True,
                    "content": {"application/json": {"schema": schema}},
                }
            cleaned["responses"] = {"200": {"description": "OK"}}
            cleaned["security"] = [{"bearerAuth": []}]
            paths.setdefault(path, {})[method.lower()] = cleaned
    return {
        "openapi": raw.get("openapi", "3.1.0"),
        "info": raw.get("info", {}),
        "servers": raw.get("servers", []),
        "paths": paths,
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
    }
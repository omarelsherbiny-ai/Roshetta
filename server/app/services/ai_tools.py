# server/app/services/ai_tools.py
"""
Runs the read tools that MicroMind may ask for, through the app's own endpoints.

The model supplies only a tool name and arguments. Every call is made in-process
against the FastAPI app with the signed-in user's own Authorization header, so
token checks, scopes and pharmacy isolation run exactly as for the browser. The
endpoint, not this module, decides what the user may see.

What this module adds on top:
  - only tools listed in shared-schema/micromind_tools.json can run;
  - only the arguments declared there are accepted (never pharmacy_id, user_id,
    a token, a role or a scope), with types, enums and limits checked;
  - at most `max_tool_calls_per_message` calls per executor;
  - results are filtered before any text goes back to the model: sensitive keys
    removed, phone-like numbers, IDs and emails scrubbed, size capped;
  - model-caused problems come back as {"ok": False, "error": ...} with a fixed
    message (endpoint error details are never forwarded).
"""
import json
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx

from server.app.services.scrub import scrub_for_external

MANIFEST_PATH = Path(__file__).resolve().parents[3] / "shared-schema" / "micromind_tools.json"
INTERNAL_BASE_URL = "http://roshetta.internal"
CALL_TIMEOUT_SECONDS = 10.0
MAX_RESULT_ITEMS = 25
MAX_RESULT_CHARS = 8000
MAX_STRING_CHARS = 300
MAX_ARGUMENT_STRING_CHARS = 200

_STATUS_MESSAGES = {
    401: "Authentication failed.",
    403: "This account is not allowed to use this tool.",
    404: "Nothing found.",
    409: "No pharmacy is selected for this session.",
    422: "The arguments were not valid for this tool.",
}

_manifest_cache: Optional[dict] = None


def load_manifest(path: Optional[Path] = None) -> dict:
    """Read the generated manifest (cached for the default path)."""
    global _manifest_cache
    if path is None:
        if _manifest_cache is None:
            _manifest_cache = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return _manifest_cache
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _is_sensitive_key(key: str, never_keys: set) -> bool:
    lowered = str(key).lower()
    return lowered in never_keys or "profit" in lowered


def filter_result(value: Any, never_keys: set) -> tuple:
    """Return (filtered value, truncated flag). Pure function, no I/O."""
    truncated = False

    def walk(node: Any) -> Any:
        nonlocal truncated
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items() if not _is_sensitive_key(k, never_keys)}
        if isinstance(node, list):
            if len(node) > MAX_RESULT_ITEMS:
                truncated = True
            return [walk(v) for v in node[:MAX_RESULT_ITEMS]]
        if isinstance(node, str):
            text = scrub_for_external(node)
            if len(text) > MAX_STRING_CHARS:
                truncated = True
                text = text[:MAX_STRING_CHARS]
            return text
        return node

    return walk(value), truncated


def _fail(message: str) -> dict:
    return {"ok": False, "error": message}


def _coerce(value: Any, spec: dict) -> Any:
    """Check one argument against its declared type and limits; raise ValueError."""
    kind = spec.get("type", "string")
    if kind == "integer":
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            value = int(value)
        if not isinstance(value, int):
            raise ValueError
    elif kind == "number":
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, str):
            value = float(value)
        if not isinstance(value, (int, float)):
            raise ValueError
    elif kind == "boolean":
        if not isinstance(value, bool):
            raise ValueError
    elif kind == "string":
        if not isinstance(value, str):
            raise ValueError
        limit = min(spec.get("maxLength", MAX_ARGUMENT_STRING_CHARS), MAX_ARGUMENT_STRING_CHARS)
        if len(value) > limit:
            raise ValueError
    else:
        raise ValueError  # objects and arrays are not accepted as arguments
    if "enum" in spec and value not in spec["enum"]:
        raise ValueError
    if kind in ("integer", "number"):
        if "minimum" in spec and value < spec["minimum"]:
            raise ValueError
        if "maximum" in spec and value > spec["maximum"]:
            raise ValueError
    return value


class AiToolExecutor:
    """One executor per chat message: it owns the call counter."""

    def __init__(self, app: Any, authorization: Optional[str], manifest: Optional[dict] = None):
        self.app = app
        self.authorization = authorization
        self.manifest = manifest if manifest is not None else load_manifest()
        self.calls = 0
        self._tools = {t["name"]: t for t in self.manifest["tools"]}
        self._never_keys = {k.lower() for k in self.manifest["never_return_keys"]}
        self._denied = {n.lower() for n in self.manifest.get("denied_argument_names", [])}
        self._forbidden = list(self.manifest.get("forbidden_path_prefixes", []))
        self._max_calls = int(self.manifest["execution"]["max_tool_calls_per_message"])

    def tool_names(self) -> list:
        return list(self._tools)

    def _build_request(self, tool: dict, arguments: dict) -> tuple:
        """Validate arguments; return (path, query, body). Raises ValueError."""
        declared = {p["name"]: p for p in tool.get("parameters", [])}
        body_spec = tool.get("body")
        for key in arguments:
            if str(key).lower() in self._denied:
                raise ValueError
            if key not in declared and not (key == "body" and body_spec):
                raise ValueError

        path = tool["path"]
        query: dict = {}
        for name, spec in declared.items():
            if name not in arguments or arguments[name] is None:
                if spec.get("required"):
                    raise ValueError
                continue
            value = _coerce(arguments[name], spec)
            if spec["in"] == "path":
                path = path.replace("{" + name + "}", quote(str(value), safe=""))
            else:
                query[name] = value

        body = None
        if body_spec is not None:
            raw_body = arguments.get("body")
            if not isinstance(raw_body, dict):
                raise ValueError
            body = {}
            for key, value in raw_body.items():
                if str(key).lower() in self._denied or key not in body_spec["properties"]:
                    raise ValueError
                body[key] = _coerce(value, body_spec["properties"][key])
            if any(r not in body for r in body_spec.get("required", [])):
                raise ValueError
        if "{" in path:
            raise ValueError
        return path, query, body

    async def call(self, name: Any, arguments: Any) -> dict:
        if self.calls >= self._max_calls:
            return _fail("Tool call limit reached for this message.")
        self.calls += 1

        tool = self._tools.get(name) if isinstance(name, str) else None
        if tool is None or tool.get("kind") != "read" or tool.get("method") not in ("GET", "POST"):
            return _fail("Unknown tool.")
        if any(tool["path"].startswith(prefix) for prefix in self._forbidden):
            return _fail("Unknown tool.")
        if not self.authorization:
            return _fail("Authentication required.")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return _fail(_STATUS_MESSAGES[422])
        try:
            path, query, body = self._build_request(tool, arguments)
        except (ValueError, TypeError):
            return _fail(_STATUS_MESSAGES[422])

        try:
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(
                transport=transport, base_url=INTERNAL_BASE_URL, timeout=CALL_TIMEOUT_SECONDS
            ) as client:
                response = await client.request(
                    tool["method"],
                    path,
                    params=query or None,
                    json=body,
                    headers={"Authorization": self.authorization},
                )
        except Exception:
            return _fail("The tool is unavailable right now.")

        if response.status_code != 200:
            return _fail(_STATUS_MESSAGES.get(response.status_code, "The tool request failed."))
        try:
            payload = response.json()
        except ValueError:
            return _fail("The tool request failed.")

        data, truncated = filter_result(payload, self._never_keys)
        if len(json.dumps(data, ensure_ascii=False)) > MAX_RESULT_CHARS:
            return _fail("The result is too large; ask for something narrower.")
        return {"ok": True, "data": data, "truncated": truncated}
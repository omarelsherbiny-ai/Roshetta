# scripts/export_openapi.py
"""
Writes shared-schema/openapi.json: the checked-in API contract of the main FastAPI app.

tests/test_openapi_contract.py imports CONTRACT_PATH and render_contract() from here.

Usage (project root, server venv python):
    python scripts/export_openapi.py            # write the file
    python scripts/export_openapi.py --check    # fail if the file is stale

--check also says whether a stale file differs only in formatting (same JSON content)
or in real content, and lists the paths that differ.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Same defaults as the tests, so the export never needs a real .env or a real database.
os.environ.setdefault("SERVER_SECRET_KEY", "roshetta-openapi-contract-test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SEED_DEMO_DATA", "false")
os.environ.setdefault("USE_MICROMIND", "false")
os.environ.setdefault("OCR_PROVIDER", "disabled")

CONTRACT_PATH = ROOT / "shared-schema" / "openapi.json"

# Endpoints that stay in the contract only to answer 410 Gone.
RETIRED_ENDPOINTS = (("/api/auth/join", "post"), ("/api/auth/invite", "post"))


def build_contract() -> dict:
    from server.app.main import app  # imported late: it needs the env defaults above

    spec = json.loads(json.dumps(app.openapi()))  # deep copy, so the app's cache is untouched

    # The bearer scheme documents auth: an operation that carried FastAPI's Authorization
    # header parameter loses it and gets a security requirement instead (an empty
    # "parameters" list stays, as in the checked-in file).
    for path_item in spec.get("paths", {}).values():
        for operation in path_item.values():
            if not (isinstance(operation, dict) and isinstance(operation.get("parameters"), list)):
                continue
            kept = [
                p for p in operation["parameters"]
                if not (p.get("in") == "header" and str(p.get("name", "")).lower() == "authorization")
            ]
            if len(kept) != len(operation["parameters"]):
                operation["parameters"] = kept
                operation.setdefault("security", [{"RoshettaBearer": []}])

    schemes = spec.setdefault("components", {}).setdefault("securitySchemes", {})
    schemes["RoshettaBearer"] = {"type": "http", "scheme": "bearer"}

    for path, method in RETIRED_ENDPOINTS:
        operation = spec.get("paths", {}).get(path, {}).get(method)
        if operation is not None:
            operation.setdefault("responses", {}).setdefault("410", {"description": "Gone"})
    return spec


def render_contract() -> str:
    return json.dumps(build_contract(), indent=2, ensure_ascii=False) + "\n"


def _first_difference(old, new, where="#"):
    """Return (location, old value, new value) of the first difference, or None."""
    if type(old) is not type(new):
        return where, old, new
    if isinstance(old, dict):
        for key in old:
            if key not in new:
                return f"{where}/{key}", old[key], "<missing>"
        for key in new:
            if key not in old:
                return f"{where}/{key}", "<missing>", new[key]
        for key in old:
            found = _first_difference(old[key], new[key], f"{where}/{key}")
            if found:
                return found
        return None
    if isinstance(old, list):
        if len(old) != len(new):
            return f"{where} (list length)", len(old), len(new)
        for index, (a, b) in enumerate(zip(old, new)):
            found = _first_difference(a, b, f"{where}/{index}")
            if found:
                return found
        return None
    return None if old == new else (where, old, new)


def _describe_difference(old_text: str, new_text: str) -> str:
    try:
        old, new = json.loads(old_text), json.loads(new_text)
    except ValueError:
        return "the checked-in file is not valid JSON"
    if old == new:
        return "same JSON content, only the formatting differs (indent, key order or escaping)"
    old_paths, new_paths = old.get("paths", {}), new.get("paths", {})
    added = sorted(set(new_paths) - set(old_paths))
    removed = sorted(set(old_paths) - set(new_paths))
    changed = sorted(p for p in set(old_paths) & set(new_paths) if old_paths[p] != new_paths[p])
    lines = ["real content differs"]
    if added:
        lines.append("  new in the app: " + ", ".join(added))
    if removed:
        lines.append("  only in the file: " + ", ".join(removed))
    if changed:
        lines.append("  changed paths: " + ", ".join(changed))
    if old.get("components") != new.get("components"):
        lines.append("  components (schemas or security schemes) differ")
    first = _first_difference(old, new)
    if first:
        where, a, b = first
        lines.append(f"  first difference at {where}")
        lines.append(f"    file: {json.dumps(a, ensure_ascii=False)[:300]}")
        lines.append(f"    app:  {json.dumps(b, ensure_ascii=False)[:300]}")
    return "\n".join(lines)


def main():
    text = render_contract()
    if "--check" in sys.argv:
        if not CONTRACT_PATH.exists():
            raise SystemExit(f"{CONTRACT_PATH} is missing; run scripts/export_openapi.py")
        current = CONTRACT_PATH.read_text(encoding="utf-8")
        if current != text:
            raise SystemExit(
                f"{CONTRACT_PATH.name} is stale; run scripts/export_openapi.py\n"
                + _describe_difference(current, text)
            )
        print(f"{CONTRACT_PATH.name} is up to date")
        return
    CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONTRACT_PATH, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"wrote {CONTRACT_PATH}")


if __name__ == "__main__":
    main()
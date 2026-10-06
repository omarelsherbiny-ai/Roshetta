# scripts/export_ai_openapi.py
"""
Writes shared-schema/micromind_openapi.yaml: the file to give AiMicroMind's OpenAPI Toolkit.

It is the same document the running server publishes at <AI_PUBLIC_URL>/ai/openapi.json:
the twelve toolkit tools of the nineteen AI operations (seven reads plus the five propose_* tools that only prepare a card; see TOOLKIT_OPERATION_IDS), a bearer scheme, no Authorization parameter, no $ref. The running server still publishes all nineteen at <AI_PUBLIC_URL>/ai/openapi.json: import THIS yaml in the toolkit, not that json.
The public base URL comes from AI_PUBLIC_URL in server/.env (it goes into `servers`).
The tunnel URL is never written into shared-schema/micromind_tools.yaml.

Usage (project root, server venv python):
    python scripts/export_ai_openapi.py            # write the file
    python scripts/export_ai_openapi.py --check    # fail if the file is stale
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_micromind_tools import emit_dict  # noqa: E402  (same small YAML writer, no PyYAML needed)
from server.app.api.ai import create_ai_app  # noqa: E402
from server.app.config import settings  # noqa: E402
from server.app.services.ai_spec import toolkit_spec  # noqa: E402

OUT = ROOT / "shared-schema" / "micromind_openapi.yaml"
EXPECTED_OPERATION_IDS = {
    "search_inventory", "match_product", "get_item_batches", "get_item_price_history",
    "get_inventory_summary", "list_categories",
    "list_ledger_entries", "get_sales_summary", "list_records_timeline",
    "list_supplier_payables", "get_payables_summary",
    "get_my_activity", "list_roles", "get_pharmacy_summary",
    "propose_product", "propose_category", "propose_product_update", "propose_restock", "propose_invite",
}


# What the toolkit gets (Session 126): 12 of the 19 operations, to keep every model request small
# (Groq free tier: 8000 tokens per minute). The other routes stay in the app for the web.
# search_inventory covers low stock, out of stock, category and expiring; get_pharmacy_summary
# covers the stock totals and what is owed to suppliers.
TOOLKIT_OPERATION_IDS = {
    "search_inventory", "match_product", "get_pharmacy_summary",
    "list_ledger_entries", "get_sales_summary", "list_supplier_payables", "list_records_timeline",
    "propose_product", "propose_product_update", "propose_category", "propose_restock", "propose_invite",
}


def build_text() -> str:
    base = settings.AI_PUBLIC_URL.strip().rstrip("/")
    if not base.startswith("https://"):
        raise SystemExit("Set AI_PUBLIC_URL=https://<your tunnel host> in server/.env first.")
    # FastAPI's raw output still has $ref, 422 responses and titles; toolkit_spec() is the
    # cleaning step the toolkit reads (running it on an already clean spec changes nothing).
    spec = toolkit_spec(create_ai_app(base).openapi())

    ids = [op["operationId"] for methods in spec["paths"].values() for op in methods.values()]
    if len(ids) != len(set(ids)) or set(ids) != EXPECTED_OPERATION_IDS:
        extra = sorted(set(ids) - EXPECTED_OPERATION_IDS)
        missing = sorted(EXPECTED_OPERATION_IDS - set(ids))
        raise SystemExit(f"Unexpected operations in the AI spec: extra={extra} missing={missing} all={sorted(ids)}")
    if spec["servers"][0]["url"] != f"{base}/ai":
        raise SystemExit("The spec's servers entry does not match AI_PUBLIC_URL.")
    for path, methods in spec["paths"].items():
        if path.startswith("/api"):
            raise SystemExit(f"Main-API path in the AI spec: {path}")
    # Keep only the toolkit's operations (the full spec was validated above) and drop any
    # leftover component schemas of the removed ones; the bearer scheme stays.
    slim_paths = {}
    for path, methods in spec["paths"].items():
        kept = {m: op for m, op in methods.items() if op["operationId"] in TOOLKIT_OPERATION_IDS}
        if kept:
            slim_paths[path] = kept
    spec = {**spec, "paths": slim_paths}
    if isinstance(spec.get("components"), dict):
        spec["components"] = {k: v for k, v in spec["components"].items() if k == "securitySchemes"}
    kept_ids = {op["operationId"] for methods in spec["paths"].values() for op in methods.values()}
    if kept_ids != TOOLKIT_OPERATION_IDS:
        raise SystemExit(f"Toolkit operations missing from the spec: {sorted(TOOLKIT_OPERATION_IDS - kept_ids)}")
    flat = "\n".join(emit_dict(spec))
    # propose_product and propose_product_update take a buy price the user typed as INPUT
    # (their bodies), so those two operations may mention unit_buy_price; every other
    # operation must never name it.
    buy_price_inputs = ("/propose-product", "/propose-product-update")
    propose_paths = {path: methods for path, methods in spec["paths"].items() if path in buy_price_inputs}
    other_paths = {path: methods for path, methods in spec["paths"].items() if path not in buy_price_inputs}
    checks = (
        (other_paths, ("$ref", "unit_buy_price", "confirmed_by", "notes", "authorization")),
        (propose_paths, ("$ref", "confirmed_by", "notes", "authorization")),
    )
    for part, words in checks:
        part_text = "\n".join(emit_dict({**spec, "paths": part}))
        for bad in words:
            if bad in part_text:
                at = part_text.index(bad)
                context = part_text[max(0, at - 400):at + 200]
                raise SystemExit(f"'{bad}' found in the AI spec; fix ai.py before exporting.\n--- context ---\n{context}\n---------------")

    header = "# shared-schema/micromind_openapi.yaml  (GENERATED by scripts/export_ai_openapi.py, do not edit)\n"
    return header + flat + "\n"


def main():
    text = build_text()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            raise SystemExit(f"{OUT.name} is stale; run scripts/export_ai_openapi.py")
        print(f"{OUT.name} is up to date")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
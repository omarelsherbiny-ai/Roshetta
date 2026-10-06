# scripts/patch_ai_search_summary.py
"""One-time patch: tell the toolkit (through the /ai spec) that search_inventory with no
search lists every product. Edits server/app/api/ai.py only. Run from the project root:
    python scripts/patch_ai_search_summary.py
Then: python scripts/export_ai_openapi.py   (rewrites shared-schema/micromind_openapi.yaml)
"""
from pathlib import Path

path = Path("server/app/api/ai.py")
text = path.read_text(encoding="utf-8")

old_summary = 'summary="Search this pharmacy\'s products by name, active ingredient or barcode",'
new_summary = (
    'summary="List or search this pharmacy\'s products. Leave search and category empty to list '
    'ALL products (alphabetical, up to limit 50); or search by name, active ingredient or barcode",'
)
old_search = 'search: Optional[str] = Query(default=None, max_length=100),'
new_search = (
    'search: Optional[str] = Query(default=None, max_length=100, description="Optional. '
    'Leave empty to list all products."),'
)

for old, new in ((old_summary, new_summary), (old_search, new_search)):
    if text.count(old) != 1:
        raise SystemExit(f"Expected exactly one match, found {text.count(old)} for: {old[:60]}")
    text = text.replace(old, new)

path.write_text(text, encoding="utf-8")
print("server/app/api/ai.py patched.")
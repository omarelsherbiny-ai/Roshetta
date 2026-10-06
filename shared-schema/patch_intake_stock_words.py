# scripts/patch_intake_stock_words.py
"""One-time patch: "what is all in inventory" and "show all products" become a stock
question (intent query_stock) instead of general chat. Edits agents/agents/intake.py only.
Run from the project root:
    python scripts/patch_intake_stock_words.py
Then: python -m pytest tests -q
"""
from pathlib import Path

path = Path("agents/agents/intake.py")
text = path.read_text(encoding="utf-8")

old = '["نواقص", "ناقص", "نفاد", "مخزون", "قرب يخلص", "بديل", "low stock", "stock", "shortage"]'
new = (
    '["نواقص", "ناقص", "نفاد", "مخزون", "المخزن", "قرب يخلص", "بديل", "كل المنتجات", '
    '"low stock", "stock", "shortage", "inventory", "all products"]'
)
if text.count(old) != 1:
    raise SystemExit(f"Expected exactly one match, found {text.count(old)}.")
path.write_text(text.replace(old, new), encoding="utf-8")
print("agents/agents/intake.py patched.")
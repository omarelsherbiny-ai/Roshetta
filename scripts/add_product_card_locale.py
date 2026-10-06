# scripts/add_product_card_locale.py
# Adds the add-product card keys to web/src/locales/ar.json and en.json.
# Never changes a key that already exists. Run from the project root: python scripts/add_product_card_locale.py
import json
from pathlib import Path

KEYS = {
    "en": {
        "pc_name": "Product name",
        "pc_buy": "Buy price",
        "pc_sell": "Sell price",
        "pc_qty": "Opening stock",
        "pc_min": "Low-stock level",
        "pc_category": "Category",
        "pc_done_editing": "Done editing",
        "pc_save_anyway": "Save anyway",
        "pc_bad_values": "Enter a name, a sell price above 0, and whole numbers for stock and low-stock level.",
    },
    "ar": {
        "pc_name": "اسم المنتج",
        "pc_buy": "سعر الشراء",
        "pc_sell": "سعر البيع",
        "pc_qty": "الكمية الافتتاحية",
        "pc_min": "حد التنبيه للمخزون",
        "pc_category": "التصنيف",
        "pc_done_editing": "تم التعديل",
        "pc_save_anyway": "احفظ على أي حال",
        "pc_bad_values": "أدخل اسماً وسعر بيع أكبر من صفر، وأعداداً صحيحة للكمية وحد التنبيه.",
    },
}

for folder in (Path("web/src/locales"), Path("locales"), Path("web/locales")):
    if (folder / "ar.json").exists():
        break
else:
    raise SystemExit("ar.json not found: run from the project root")

for lang, keys in KEYS.items():
    path = folder / f"{lang}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    added = [k for k in keys if k not in data]
    for k in added:
        data[k] = keys[k]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{path}: added {len(added)} of {len(keys)} keys")
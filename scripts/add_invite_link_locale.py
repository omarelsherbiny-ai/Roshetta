# scripts/add_invite_link_locale.py
"""Adds the 5 `ia_*` keys (invitation link shown after Confirm) to the Arabic and English locale
files. Never changes an existing key. Run from the project root: python scripts/add_invite_link_locale.py"""
import json
import pathlib
import sys

KEYS = {
    "ar": {
        "ia_link": "رابط الدعوة",
        "ia_copy": "نسخ",
        "ia_copied": "تم النسخ",
        "ia_expires": "صالح حتى",
        "ia_once": "انسخه الآن: يظهر مرة واحدة فقط.",
        "ia_missing": "تم إنشاء الدعوة لكن الرابط لم يصل. أنشئ دعوة جديدة من صفحة الأعضاء.",
    },
    "en": {
        "ia_link": "Invitation link",
        "ia_copy": "Copy",
        "ia_copied": "Copied",
        "ia_expires": "Valid until",
        "ia_once": "Copy it now: it is shown only once.",
        "ia_missing": "The invitation was created, but the link did not arrive. Create a new one from the Members page.",
    },
}

root = pathlib.Path(".")
for code, keys in KEYS.items():
    found = [p for p in root.glob(f"web/**/{code}.json") if "node_modules" not in p.parts and ".next" not in p.parts and p.parent.name == "locales"]
    if len(found) != 1:
        sys.exit(f"expected one locales/{code}.json under web/, found {len(found)}: {found}")
    path = found[0]
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    indent = 4 if text.lstrip("{").startswith("\n    \"") else 2
    added = [k for k in keys if k not in data]
    for k in added:
        data[k] = keys[k]
    if added:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=indent) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
    print(f"{path}: added {len(added)} of {len(keys)} keys")
# scripts/add_member_remove_locale.py (adds the 7 mb_rm_* / mb_toast_dismiss keys to the ar and en locale files; never changes an existing key)
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEW = {
    "ar": {
        "mb_rm_title": "إزالة العضو؟",
        "mb_rm_confirm": "إزالة",
        "mb_rm_cancel": "إلغاء",
        "mb_rm_retry": "إعادة المحاولة",
        "mb_rm_busy": "جارٍ الإزالة...",
        "mb_rm_done": "تمت إزالة العضو",
        "mb_toast_dismiss": "إغلاق",
    },
    "en": {
        "mb_rm_title": "Remove this member?",
        "mb_rm_confirm": "Remove",
        "mb_rm_cancel": "Cancel",
        "mb_rm_retry": "Try again",
        "mb_rm_busy": "Removing...",
        "mb_rm_done": "Member removed",
        "mb_toast_dismiss": "Dismiss",
    },
}

for lang, keys in NEW.items():
    path = ROOT / "web" / "src" / "locales" / f"{lang}.json"
    text = path.read_text(encoding="utf-8")
    match = re.search(r"\n( +|\t)\"", text)
    indent = match.group(1) if match else "  "
    data = json.loads(text)
    added = [k for k in keys if k not in data]
    for k in added:
        data[k] = keys[k]
    if added:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8")
    print(f"{lang}: added {len(added)} key(s), kept {len(keys) - len(added)} existing")

if __name__ == "__main__":
    sys.exit(0)
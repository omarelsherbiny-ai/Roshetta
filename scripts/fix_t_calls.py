# scripts/fix_t_calls.py (one-off: turns t.some_key into t('some_key'))
# Usage from the project root:
#   python scripts/fix_t_calls.py            -> dry run over web/src, changes nothing
#   python scripts/fix_t_calls.py --apply    -> rewrites the files, backups in scripts/t_backup/
#   python scripts/fix_t_calls.py --apply web/src/app/records/page.tsx   -> only the files named
import json
import pathlib
import re
import sys

PATTERN = re.compile(r"(?<![\w.$])t\.([A-Za-z_]\w*)")
LOCAL_T = re.compile(r"\b(?:const|let|var)\s+t\s*=")
keys = set(json.loads(pathlib.Path("web/src/locales/en.json").read_text(encoding="utf-8")))

args = [a for a in sys.argv[1:] if a != "--apply"]
apply = "--apply" in sys.argv
files = [pathlib.Path(a) for a in args] or sorted(pathlib.Path("web/src").rglob("*.tsx"))
backup = pathlib.Path("scripts/t_backup")

total = 0
for path in files:
    text = path.read_text(encoding="utf-8")
    found = PATTERN.findall(text)
    if not found:
        continue
    if "useLanguage" not in text or LOCAL_T.search(text):
        print(f"SKIPPED {path}: {len(found)} hits but `t` is not from useLanguage (own definition?), check by hand")
        continue
    unknown = sorted({k for k in found if k not in keys})
    total += len(found)
    print(f"{path}: {len(found)} {'replaced' if apply else 'would be replaced'}")
    if unknown:
        print("   keys NOT in en.json:", ", ".join(unknown))
    if apply:
        backup.mkdir(parents=True, exist_ok=True)
        (backup / ("__".join(path.parts) + ".bak")).write_text(text, encoding="utf-8")
        path.write_text(PATTERN.sub(lambda m: f"t('{m.group(1)}')", text), encoding="utf-8")

print(f"total: {total}" + ("" if apply else "  (dry run, nothing changed; add --apply)"))
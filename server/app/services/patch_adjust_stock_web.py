# scripts/patch_adjust_stock_web.py  (run from the project root: python scripts/patch_adjust_stock_web.py)
# Wires the adjust_stock card into the assistant page: no Modify button, and the card shows the
# server's own summary text (it wraps, like the other change cards). Non-visual: no new layout.
# All-or-nothing, safe to run twice. Keep it in scripts/, not tests/.
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EDITS = [
    ("web/src/app/assistant/page.tsx",
     "const ITEMLESS_TYPES: readonly string[] = ['update_product', 'create_category', 'create_invite'];",
     "const ITEMLESS_TYPES: readonly string[] = ['update_product', 'create_category', 'create_invite', 'adjust_stock'];"),
    ("web/src/app/assistant/page.tsx",
     "msg.proposal.action_type === 'create_invite' ? 'person_add' : 'point_of_sale'",
     "msg.proposal.action_type === 'create_invite' ? 'person_add' : msg.proposal.action_type === 'adjust_stock' ? 'inventory_2' : 'point_of_sale'"),
    ("web/src/types/index.ts",
     "  | 'create_invite'\n",
     "  | 'create_invite'\n  | 'adjust_stock'\n"),
]


def main():
    texts, applied, skipped = {}, 0, 0
    for rel, old, new in EDITS:
        path = ROOT / rel
        if rel not in texts:
            if not path.exists():
                sys.exit(f"Missing file: {rel}. Nothing was changed.")
            texts[rel] = path.read_text(encoding="utf-8")
        text = texts[rel]
        if new in text:
            skipped += 1
            continue
        if text.count(old) != 1:
            sys.exit(f"Expected text found {text.count(old)} times (need 1) in {rel}:\n{old[:100]!r}\nNothing was changed.")
        texts[rel] = text.replace(old, new)
        applied += 1
    for rel, text in texts.items():
        (ROOT / rel).write_text(text, encoding="utf-8")
    print(f"Done: {applied} edits applied, {skipped} already in place.")


if __name__ == "__main__":
    main()
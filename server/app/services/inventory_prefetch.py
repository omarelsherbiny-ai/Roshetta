# server/app/services/inventory_prefetch.py
"""Plain inventory reads answered in ONE model turn (Session 125, speed).

A tool turn costs two model turns plus the tool call through the tunnel (Omar: tool answers
are far slower and hit the 25 s timeout). For a plain read (list, low stock, stock summary)
the server already holds the data, so it puts a compact list into the question and the flow
answers in one short turn, with no tool call. Pure functions, no database, no settings.

What leaves the system is what the /ai tools return: the name in the answer's language,
the category, the stock and the sell price. Never buy prices, ids, batches or barcodes.
"""
import re
from typing import Any, Iterable, Optional

# More than this many products and an "all" question goes to the tools instead: a cut list
# could not answer a question about one product that was cut.
MAX_ALL_ROWS = 60
# A low-stock list longer than this is cut and says how many are not shown.
MAX_LOW_ROWS = 40

_LOW_WORDS = ["low stock", "shortage", "out of stock", "running out", "نواقص", "ناقص", "نفاد", "قرب يخلص"]
_ALT_WORDS = ["بديل", "alternative", "substitute", "instead of"]
_INV_WORDS = ["inventory", "products", "items", "stock", "مخزون", "المخزن", "المنتجات", "منتجات", "الأصناف", "الاصناف", "أصناف"]
_LIST_RE = re.compile(
    r"(?<!\w)(?:show|list|display|give|get|retrieve|see|view|check|what|which|all|everything|summary|"
    r"اعرض|عرض|وريني|طلعلي|هاتلي|هات|كل|ايه|إيه|عندي|عندنا|ملخص)(?!\w)",
    re.IGNORECASE,
)


def _normalize_digits(text: str) -> str:
    return text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))


def prefetch_mode(text: str) -> Optional[str]:
    """'low', 'all' or None (None: keep the tools).

    A digit (a quantity or an id) or an alternative-medicine word means the question is
    about something specific, so it keeps the tools.
    """
    q = _normalize_digits(text or "").lower()
    if re.search(r"\d", q) or any(w in q for w in _ALT_WORDS):
        return None
    if any(w in q for w in _LOW_WORDS):
        return "low"
    if any(w in q for w in _INV_WORDS) and _LIST_RE.search(q):
        return "all"
    return None


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_inventory_question(
    user_text: str,
    response_language: str,
    items: Iterable[dict],
    lang: str,
    mode: str,
) -> Optional[str]:
    """The one-turn question, or None when the tools should answer instead."""
    items = list(items)
    if mode == "all" and len(items) > MAX_ALL_ROWS:
        return None
    rows = []
    for it in sorted(items, key=lambda x: str(x.get("name_en") or x.get("name_ar") or "").lower()):
        qty, floor = _num(it.get("stock_qty")), _num(it.get("min_threshold"))
        if mode == "low" and not qty <= floor:
            continue
        first, second = ("name_ar", "name_en") if lang == "ar" else ("name_en", "name_ar")
        name = str(it.get(first) or it.get(second) or "?")
        cat = str(it.get("category") or "").strip()
        rows.append((name, cat, qty, _num(it.get("unit_sell_price"))))

    shown = rows[:MAX_LOW_ROWS] if mode == "low" else rows
    lines = [
        f"{n}. {name} | category: {cat or '-'} | stock: {qty:g} | sell price: {price:g} EGP"
        for n, (name, cat, qty, price) in enumerate(shown, 1)
    ]
    if mode == "low":
        header = f"Low-stock products (stock at or below the minimum): {len(rows)} of {len(items)} products."
        if len(rows) > len(shown):
            header += f" Only the first {len(shown)} are listed; say that {len(rows) - len(shown)} more are not shown."
    else:
        header = f"All products: {len(items)}. The list is complete."
    body = "\n".join(lines) if lines else "(no rows: tell the user there are none)"
    return (
        f"Answer in {response_language}.\n"
        "The app already read this pharmacy's inventory. Do not call any tool; use only this data.\n"
        f"{header}\n{body}\n"
        "Format: a plain numbered list, one line per product (name, category if any, stock, "
        "sell price in EGP), no table, no markdown, no ids. For a summary question give the "
        "counts and the products that need attention.\n"
        f"User question:\n{user_text}"
    )
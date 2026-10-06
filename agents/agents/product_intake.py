# agents/agents/product_intake.py
"""Reads a "add a new product" message from the assistant chat (Waiting task 6b).

Plain Python, no database. `product_gate` runs first in the graph: when the message
asks to add a product it sets intent `create_product` and a `product_draft`;
otherwise the state goes on to the normal intake agent unchanged.

Session 119: a one-letter typo in the product word ("prodcut", "prodact") is corrected
before matching, so the message still reaches the confirm card instead of the chat model.
"""
import re
from typing import Any, Dict, Optional

from agents.state import AgentState

_EASTERN = "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹"
_WESTERN = "01234567890123456789"

_EN_TRIGGER = re.compile(
    r"\b(?:add|create|register|insert)\b.*\b(?:product|item|medicine|drug)\b|\bnew\s+(?:product|medicine|drug)\b",
    re.IGNORECASE | re.DOTALL,
)
_AR_TRIGGERS = [
    "أضف منتج", "اضف منتج", "أضيف منتج", "اضيف منتج", "منتج جديد", "صنف جديد", "دواء جديد",
    "أضف صنف", "اضف صنف", "أضيف صنف", "اضيف صنف", "إضافة منتج", "اضافة منتج", "إضافة صنف", "اضافة صنف",
    "أضف دواء", "اضف دواء",
]
_QUESTION_START = re.compile(r"^\s*(?:how|where|what|why|كيف|ازاي|إزاي|فين|ايه|إيه)\b", re.IGNORECASE)
_RESTOCK_WORDS = ["restock", "توريد", "طلبية", "شحنة", "استلمت"]

_NUM = r"(\d+(?:\.\d+)?)"
_SELL_RE = re.compile(
    r"(?:selling\s+price|sell(?:ing)?(?:\s+price)?|سعر\s+البيع|بيع|للبيع)\s*(?:is|=|:|ب|بـ)?\s*" + _NUM,
    re.IGNORECASE,
)
_BUY_RE = re.compile(
    r"(?:buy(?:ing)?(?:\s+price)?|cost(?:\s+price)?|purchase(?:\s+price)?|price|سعر\s+الشراء|شراء|سعر|بسعر)\s*(?:is|=|:|ب|بـ)?\s*" + _NUM,
    re.IGNORECASE,
)
_QTY_RE = re.compile(r"(?:qty|quantity|stock|الكمية|كمية|عدد)\s*(?:is|=|:)?\s*" + _NUM, re.IGNORECASE)
_MIN_RE = re.compile(
    r"(?:min(?:imum)?(?:\s+(?:stock|level|threshold))?|reorder(?:\s+level)?|low\s+stock|حد\s+الطلب(?:\s+الأدنى)?|"
    r"الحد\s+الأدنى(?:\s+للنواقص)?|حد\s+النواقص)\s*(?:is|=|:)?\s*" + _NUM,
    re.IGNORECASE,
)
_CAT_RE = re.compile(r"(?:category|في\s+قسم|قسم|فئة|الفئة)\s*(?:is|=|:)?\s*(.+)", re.IGNORECASE | re.DOTALL)
_NAME_AFTER_LABEL = re.compile(
    r"(?:called|named|name(?:d)?(?:\s+is)?|اسمه|اسمها|باسم|اسم)\s+(.+)", re.IGNORECASE | re.DOTALL
)
_NAME_AFTER_WORD = re.compile(
    r"(?:product|item|medicine|drug|منتج|صنف|دواء)(?:\s+(?:new|جديد))?\s+(.+)", re.IGNORECASE | re.DOTALL
)
_STOP = re.compile(
    r"\b(?:price|buy|buying|cost|purchase|sell|selling|for|at|with|qty|quantity|stock|min|minimum|category|and)\b"
    r"|(?:سعر|شراء|بيع|بسعر|كمية|الكمية|وسعر|الحد|حد|قسم|فئة|ب)\s|[,،]",
    re.IGNORECASE,
)

# Words a typo may be mistaken for; a token one edit away from one of these is corrected.
_PRODUCT_WORDS = ("product", "products", "medicine")
_WORD = re.compile(r"[A-Za-z]{5,}")


def _normalize_digits(text: str) -> str:
    return text.translate(str.maketrans(_EASTERN, _WESTERN))


def _one_edit_apart(a: str, b: str) -> bool:
    """True when `a` is `b` with one letter changed, added, dropped or two neighbours swapped."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diffs = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diffs) == 1:
            return True
        return (
            len(diffs) == 2
            and diffs[1] == diffs[0] + 1
            and a[diffs[0]] == b[diffs[1]]
            and a[diffs[1]] == b[diffs[0]]
        )
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def _fix_typos(text: str) -> str:
    """Corrects a one-letter typo of the product word ("prodcut" -> "product")."""
    def repair(match: "re.Match[str]") -> str:
        word = match.group(0)
        lowered = word.lower()
        if lowered in _PRODUCT_WORDS:
            return word
        for target in _PRODUCT_WORDS:
            if _one_edit_apart(lowered, target):
                return target
        return word

    return _WORD.sub(repair, text)


def looks_like_add_product(text: str) -> bool:
    text = _fix_typos(text)
    lowered = text.lower()
    if _QUESTION_START.search(text) or any(word in lowered for word in _RESTOCK_WORDS):
        return False
    return bool(_EN_TRIGGER.search(text)) or any(phrase in text for phrase in _AR_TRIGGERS)


def _take(regex: "re.Pattern[str]", text: str):
    """First number the regex finds, and the text with that clause cut out."""
    match = regex.search(text)
    if not match:
        return None, text
    return float(match.group(1)), text[: match.start()] + " " + text[match.end():]


def _clean_name(raw: str) -> str:
    cut = _STOP.search(raw)
    if cut:
        raw = raw[: cut.start()]
    return raw.strip().strip("\"'`.،,:؛- ").strip()


def parse_product_request(text: str) -> Optional[Dict[str, Any]]:
    """The product the person asked to add, or None when the message is not that request.

    A read price word ("price 10") is the buy price; "sell 15" is the sell price.
    Missing values stay None so the caller can ask for them.
    """
    text = _fix_typos(_normalize_digits(text or "")).strip()
    if not text or not looks_like_add_product(text):
        return None

    sell, rest = _take(_SELL_RE, text)
    buy, rest = _take(_BUY_RE, rest)
    qty, rest = _take(_QTY_RE, rest)
    min_level, rest = _take(_MIN_RE, rest)
    if min_level is not None and min_level < 1:
        min_level = None

    category = None
    cat_match = _CAT_RE.search(rest)
    if cat_match:
        raw = cat_match.group(1)
        cut = _STOP.search(raw)
        consumed = raw[: cut.start()] if cut else raw
        category = _clean_name(consumed)[:50] or None
        rest = rest[: cat_match.start()] + " " + rest[cat_match.start(1) + len(consumed):]

    name = ""
    for regex in (_NAME_AFTER_LABEL, _NAME_AFTER_WORD):
        match = regex.search(rest)
        if match:
            name = _clean_name(match.group(1))
            if name:
                break
    # "add new product pandol": the word right after the product word may be "new".
    name = re.sub(r"^(?:new|جديد)[\s:،,\-]+", "", name, flags=re.IGNORECASE).strip()
    if name.lower() in {"called", "named", "name", "is"}:
        name = ""
    return {
        "name": name[:150] or None,
        "unit_buy_price": buy,
        "unit_sell_price": sell,
        "stock_qty": qty,
        "min_threshold": min_level,
        "category": category,
    }


def product_gate(state: AgentState) -> AgentState:
    draft = parse_product_request(state.get("user_query", ""))
    if draft is None:
        return state
    return {**state, "intent": "create_product", "product_draft": draft}
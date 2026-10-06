# agents/agents/intake.py
import re
from typing import Dict, Any, List
from agents.state import AgentState


# Words that make a message a financial question (checked before every other intent).
_FINANCE_WORDS = ["أرباح", "ارباح", "مبيعات اليوم", "دخلنا كام", "صافي", "profit", "sales today", "today's profit"]
# "Summary" style words: "Show today's summary", "ملخص اليوم". Ignored when the
# message also mentions stock (see _STOCK_WORDS).
_SUMMARY_WORDS = ["ملخص", "summary", "revenue", "إيراد", "ايراد"]
_STOCK_WORDS = ["مخزون", "نواقص", "ناقص", "نفاد", "stock", "inventory", "shortage"]
# "How many did I sell today?" (a question about today's sales, not a sale to log):
# needs a today word, a sell word and a question word together.
_TODAY_WORDS = ["today", "اليوم", "النهاردة", "النهارده", "انهارده"]
_SELL_WORDS = ["sell", "sold", "sales", "sale", "بعت", "بعنا", "مبيعات", "بيع"]
_QUESTION_WORDS = ["how many", "how much", "قد ايه", "قد إيه", "كام"]


# "sell price" is a price, not a sale: "سعر بيع 20", "بسعر بيع 20", "sell price 20", "sale price".
# Removed before the sale words are looked for (Session 126).
_SELL_PRICE_PHRASE = re.compile(
    r"(?<!\w)ب?سعر\s+(?:ال)?بيع(?!\w)|(?<!\w)(?:sale|sell|selling)\s+price(?!\w)",
    re.IGNORECASE,
)


def _asks_sales_today(query_lower: str) -> bool:
    query_lower = _SELL_PRICE_PHRASE.sub(" ", query_lower)
    is_question = (
        "?" in query_lower
        or "؟" in query_lower
        or any(w in query_lower for w in _QUESTION_WORDS)
        or re.search(r"(?<!\w)كم(?!\w)", query_lower) is not None
    )
    return (
        is_question
        and any(w in query_lower for w in _TODAY_WORDS)
        and any(w in query_lower for w in _SELL_WORDS)
    )


# A message that asks to SEE records ("show sales this week", "طلعلي كل المنتجات") is a
# read, not a sale to log. Weak sale words ("sale", "بيع", "طلع") must stand alone as a
# word, so "sales", "سعر البيع" and "طلعلي" no longer count; the strong verbs below
# ("sold", "بعت", ...) always count when the message has a number.
_READ_WORDS = re.compile(
    r"(?<!\w)(?:show|list|display|report|reports|records|history|what|which|how|"
    r"اعرض|عرض|وريني|طلعلي|هاتلي|هات|ايه|إيه|كل)(?!\w)",
    re.IGNORECASE,
)
_STRONG_SALE_WORDS = ["بعت", "خرجت", "صرفت", "سجل بيع", "sold"]
_WEAK_SALE_WORDS = re.compile(r"(?<!\w)(?:بيع|طلع|sale)(?!\w)", re.IGNORECASE)


def _is_sale_request(query_lower: str) -> bool:
    """True when the message asks to log a sale (not to look at past sales)."""
    has_number = re.search(r"\d", _normalize_digits(query_lower)) is not None
    if _READ_WORDS.search(query_lower) and not has_number:
        return False
    # A price phrase ("سعر بيع 20") is not a sale verb.
    cleaned = _SELL_PRICE_PHRASE.sub(" ", query_lower)
    return any(k in cleaned for k in _STRONG_SALE_WORDS) or _WEAK_SALE_WORDS.search(cleaned) is not None


def _normalize_digits(text: str) -> str:
    eastern = "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹"
    western = "01234567890123456789"
    return text.translate(str.maketrans(eastern, western))


def parse_egyptian_quantities(text: str) -> float:
    """Extract quantities from Egyptian Arabic keywords or digits."""
    text_lower = _normalize_digits(text).lower()
    if "علبتين" in text_lower or "شريطين" in text_lower or "أمبولتين" in text_lower or "ازازتين" in text_lower:
        return 2.0
    if "علبة" in text_lower or "شريط" in text_lower or "أمبول" in text_lower or "ازازة" in text_lower:
        # Check if preceded by a number, e.g. "3 علب" or "10 علب"
        num_match = re.search(r"(\d+(\.\d+)?)\s*(علب|علبة|شريط|أمبول|ازازة)", text_lower)
        if num_match:
            return float(num_match.group(1))
        return 1.0

    # General digit extraction
    num_match = re.search(r"\b(\d+(\.\d+)?)\b", text_lower)
    if num_match:
        return float(num_match.group(1))
    return 1.0


def extract_price(text: str) -> float:
    """Extract price in EGP / جنيه from text."""
    # Look for 'بـ 35' or '35 جنيه' or '35 ج' or 'بسعر 35'
    text = _normalize_digits(text)
    match = re.search(r"(?:بـ|بسعر|ب|سعر)\s*(\d+(\.\d+)?)", text)
    if match:
        return float(match.group(1))

    match2 = re.search(r"(\d+(\.\d+)?)\s*(?:جنيه|ج\.م|egp|le)", text, re.IGNORECASE)
    if match2:
        return float(match2.group(1))

    return 0.0


# Words that are not part of a product name in a sale or restock message.
_NAME_NOISE = {
    # sale / restock / log verbs
    "بعت", "بعنا", "بيع", "خرجت", "صرفت", "سجل", "طلع", "sold", "sell", "sale", "log", "register",
    "توريد", "طلبية", "شحنة", "استلمت", "بضاعة", "جديدة", "restock", "received", "receive",
    # time, people, units, filler
    "today", "اليوم", "النهاردة", "النهارده", "انهارده", "i", "we", "my", "the", "a", "an", "of",
    "for", "to", "from", "each", "item", "items", "pcs", "pc", "unit", "units", "pack", "packs",
    "box", "boxes", "علبة", "علب", "علبتين", "شريط", "شريطين", "أمبول", "أمبولتين", "ازازة",
    "ازازتين", "من", "ل", "قطعة", "قطع",
    # payment and price words
    "cash", "card", "credit", "فيزا", "كارت", "آجل", "شكك", "بسعر", "سعر", "price", "egp", "le",
    "جنيه", "ج", "ج.م",
}


def extract_product_name(text: str) -> str:
    """The product name typed in a sale or restock message ('' when there is none).

    Nothing is invented: the words are what the person typed, minus verbs, numbers, units
    and price phrases. The verification step matches the result against the real catalog.
    """
    text = _normalize_digits(text).lower()
    text = re.sub(r"(?:بـ|بسعر|ب|سعر|price)\s*\d+(?:\.\d+)?", " ", text)
    text = re.sub(r"\d+(?:\.\d+)?\s*(?:جنيه|ج\.م|egp|le)", " ", text)
    words = [w for w in re.split(r"[\s,.:;!؟?]+", text) if w and not re.fullmatch(r"\d+(?:\.\d+)?", w)]
    return " ".join(w for w in words if w not in _NAME_NOISE).strip()


# "add 5 panadol", "add for panadol 5 items", "زود بنادول 10": adding stock to a product
# that already exists is a restock, never a new product (that needs the word "product").
_ADD_WORD = r"(?<!\w)(?:add|اضف|أضف|ضيف|زود|زوّد)(?!\w)"
_ADD_FILLER = {
    "for", "to", "of", "the", "a", "an", "more", "item", "items", "pcs", "pc", "piece", "pieces",
    "unit", "units", "box", "boxes", "pack", "packs", "stock", "of", "علبة", "علب", "شريط",
    "اشرطة", "أشرطة", "قطعة", "قطع", "حبة", "حبات", "من", "ل", "الى", "إلى",
}


def _parse_add_stock(text: str):
    """Return (product_name, quantity) for an add-stock message, or None."""
    text = _normalize_digits(text).lower()
    if re.search(_ADD_WORD, text) is None:
        return None
    num = re.search(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])", text)
    if num is None:
        return None
    qty = float(num.group(1))
    if qty <= 0:
        return None
    rest = re.sub(_ADD_WORD, " ", text, count=1)
    rest = rest.replace(num.group(0), " ", 1)
    words = [w for w in re.split(r"[\s,.:;!؟?]+", rest) if w and w not in _ADD_FILLER]
    name = " ".join(words).strip()
    if not name:
        return None
    return name, qty


# "give me all in inventory", "what products do I have", "retrieve all products": a read of
# the inventory. Needs an inventory word AND a read word, and no write word, so "add a new
# product" and "change the category of ..." never land here.
_INV_LIST_WORDS = ["inventory", "المخزن", "المنتجات", "الأصناف", "الاصناف", "products"]
_INV_READ_RE = re.compile(
    r"(?<!\w)(?:show|list|display|give|get|retrieve|see|view|check|what|which|all|everything|"
    r"اعرض|عرض|وريني|طلعلي|هاتلي|هات|كل|ايه|إيه|عندي|عندنا)(?!\w)",
    re.IGNORECASE,
)
_INV_WRITE_RE = re.compile(
    r"(?<!\w)(?:add|new|create|delete|remove|edit|change|update|sell|sold|restock)(?!\w)",
    re.IGNORECASE,
)
_INV_WRITE_AR = ["اضف", "أضف", "ضيف", "زود", "جديد", "احذف", "امسح", "عدل", "غير", "بعت"]


def _asks_inventory_list(query_lower: str) -> bool:
    """True when the message asks to SEE the inventory (a read, never a write)."""
    if not any(w in query_lower for w in _INV_LIST_WORDS):
        return False
    if _INV_WRITE_RE.search(query_lower) or any(w in query_lower for w in _INV_WRITE_AR):
        return False
    return _INV_READ_RE.search(query_lower) is not None


def intake_agent(state: AgentState) -> AgentState:
    query = state.get("user_query", "").strip()
    query_lower = query.lower()

    # Default values
    intent = "general_chat"
    extracted_items: List[Dict[str, Any]] = []
    total_amount = 0.0
    payment_method = "cash"
    if "فيزا" in query_lower or "كارت" in query_lower or "card" in query_lower:
        payment_method = "card"
    elif "آجل" in query_lower or "شكك" in query_lower or "credit" in query_lower:
        payment_method = "credit"

    # Intent Detection
    # 1. Financial Query: profit and sales words, or a "summary" word when the
    # message is not about stock (a "stock summary" is an inventory question).
    asks_stock = any(k in query_lower for k in _STOCK_WORDS)
    asks_summary = not asks_stock and any(k in query_lower for k in _SUMMARY_WORDS)
    if asks_summary or _asks_sales_today(query_lower) or any(k in query_lower for k in _FINANCE_WORDS):
        intent = "query_finance"
        return {
            **state,
            "intent": intent,
        }

    # 2. Inventory / Low Stock Query
    # ``restock`` contains the substring ``stock``; exclude explicit restock
    # requests here so they reach the ledger-action parser below.
    is_restock_request = (
        any(k in query_lower for k in ["توريد", "طلبية", "شحنة", "استلمت", "بضاعة جديدة", "restock"])
        or _parse_add_stock(query) is not None
    )
    if not is_restock_request and (
        any(k in query_lower for k in ["نواقص", "ناقص", "نفاد", "مخزون", "قرب يخلص", "بديل", "low stock", "stock", "shortage"])
        or _asks_inventory_list(query_lower)
    ):
        intent = "query_stock"
        return {
            **state,
            "intent": intent,
        }

    # 3. Log Expense
    if any(k in query_lower for k in ["مصاريف", "مصروف", "كهربا", "كهرباء", "نظافة", "غدا", "ايجار", "إيجار", "صيانة", "expense"]):
        intent = "log_expense"
        price = extract_price(query)
        if price == 0.0:
            # Fallback to any number
            nums = re.findall(r"\b(\d+(\.\d+)?)\b", query)
            if nums:
                price = float(nums[0][0])
        
        # Clean item title
        title = "مصاريف عامة"
        if "كهرب" in query_lower:
            title = "فاتورة كهرباء"
        elif "ايجار" in query_lower or "إيجار" in query_lower:
            title = "إيجار الصيدلية"
        elif "نظاف" in query_lower:
            title = "مصاريف نظافة وبوفيه"
        elif "غدا" in query_lower or "أكل" in query_lower:
            title = "وجبات ومصروف عمال"
        elif "صيانة" in query_lower:
            title = "مصاريف صيانة"

        extracted_items.append({
            "item_name": title,
            "quantity": 1.0,
            "unit_price": price,
            "subtotal": price,
            "category": "Expense"
        })
        total_amount = price

        return {
            **state,
            "intent": intent,
            "extracted_items": extracted_items,
            "total_amount": total_amount,
            "payment_method": payment_method,
        }

    # 4. Log Restock
    add_stock = _parse_add_stock(query)
    if add_stock is not None or any(k in query_lower for k in ["توريد", "طلبية", "شحنة", "استلمت", "بضاعة جديدة", "restock"]):
        intent = "log_restock"
        qty = parse_egyptian_quantities(query)
        price = extract_price(query)

        # The typed product name goes on as written; the verification step matches it
        # against the real catalog (and shows suggestions when it is unsure).
        if add_stock is not None:
            item_name, qty = add_stock
        else:
            item_name = extract_product_name(query)

        extracted_items.append({
            "item_name": item_name,
            "quantity": qty,
            "unit_price": price,
            "subtotal": qty * price,
        })
        total_amount = qty * price

        return {
            **state,
            "intent": intent,
            "extracted_items": extracted_items,
            "total_amount": total_amount,
            "payment_method": payment_method,
        }

    # 5. Log Sale
    if _is_sale_request(query_lower):
        intent = "log_sale"
        qty = parse_egyptian_quantities(query)
        price = extract_price(query)

        # The typed name goes on as written. A price that was not typed stays 0: the
        # verification step then takes the real catalog sell price (oldest lot first).
        item_name = extract_product_name(query)

        extracted_items.append({
            "item_name": item_name,
            "quantity": qty,
            "unit_price": price,
            "subtotal": qty * price,
        })
        total_amount = qty * price

        return {
            **state,
            "intent": intent,
            "extracted_items": extracted_items,
            "total_amount": total_amount,
            "payment_method": payment_method,
        }

    # 6. Fallback General Chat
    fallback_text = (
        "I can help check recorded inventory, prepare sales or restock proposals, log expenses, and summarize recorded financial activity. "
        "Document extraction is currently unavailable; enter product or document details manually."
        if state.get("language") == "en" else
        "أستطيع مساعدتك في الاستعلام عن المخزون المسجل، وتجهيز مقترحات البيع أو التوريد، وتسجيل المصروفات، وتلخيص الحركات المالية المسجلة. "
        "استخراج البيانات من الصور غير متاح حالياً؛ أدخل بيانات المنتج أو المستند يدوياً."
    )
    return {
        **state,
        "intent": "general_chat",
        "answer_text": fallback_text,
    }
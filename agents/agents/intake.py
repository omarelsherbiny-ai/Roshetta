import re
from typing import Dict, Any, List
from agents.state import AgentState


MEDICINE_ALIASES = [
    ("بنادول اكسترا", "بنادول اكسترا (أحمر)"),
    ("بنادول أحمر", "بنادول اكسترا (أحمر)"),
    ("بنادول احمر", "بنادول اكسترا (أحمر)"),
    ("panadol extra", "بنادول اكسترا (أحمر)"),
    ("بنادول أزرق", "بنادول أزرق (عادي)"),
    ("بنادول ازرق", "بنادول أزرق (عادي)"),
    ("panadol blue", "بنادول أزرق (عادي)"),
    ("أوجمنتين", "أوجمنتين 1 جم أقراص"),
    ("اوجمنتين", "أوجمنتين 1 جم أقراص"),
    ("augmentin", "أوجمنتين 1 جم أقراص"),
    ("هاي بيوتك", "هاي بيوتك 1 جم"),
    ("hibiotic", "هاي بيوتك 1 جم"),
    ("كونجستال", "كونجستال أقراص للبرد"),
    ("congestal", "كونجستال أقراص للبرد"),
    ("بروفين", "بروفين 400 مجم"),
    ("brufen", "بروفين 400 مجم"),
    ("كيتوفان", "كيتوفان 50 مجم"),
    ("ketofan", "كيتوفان 50 مجم"),
    ("فلاجيل", "فلاجيل 500 مجم"),
    ("flagyl", "فلاجيل 500 مجم"),
    ("أنتينال", "أنتينال كبسول"),
    ("انتينال", "أنتينال كبسول"),
    ("antinal", "أنتينال كبسول"),
    ("أوتريفين", "أوتريفين بخاخ أنف"),
    ("اوتريفين", "أوتريفين بخاخ أنف"),
    ("otrivin", "أوتريفين بخاخ أنف"),
]


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
    # 1. Financial Query
    if any(k in query_lower for k in ["أرباح", "ارباح", "مبيعات اليوم", "دخلنا كام", "صافي", "profit", "sales today", "today's profit"]):
        intent = "query_finance"
        return {
            **state,
            "intent": intent,
        }

    # 2. Inventory / Low Stock Query
    # ``restock`` contains the substring ``stock``; exclude explicit restock
    # requests here so they reach the ledger-action parser below.
    is_restock_request = any(k in query_lower for k in ["توريد", "طلبية", "شحنة", "استلمت", "بضاعة جديدة", "restock"])
    if not is_restock_request and any(k in query_lower for k in ["نواقص", "ناقص", "نفاد", "مخزون", "قرب يخلص", "بديل", "low stock", "stock", "shortage"]):
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
    if any(k in query_lower for k in ["توريد", "طلبية", "شحنة", "استلمت", "بضاعة جديدة", "restock"]):
        intent = "log_restock"
        qty = parse_egyptian_quantities(query)
        price = extract_price(query)

        item_name = "صنف مورد"
        for alias, canonical_name in MEDICINE_ALIASES:
            if alias.lower() in query_lower:
                item_name = canonical_name
                break

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
    if any(k in query_lower for k in ["بعت", "بيع", "خرجت", "صرفت", "سجل بيع", "طلع", "sold", "sale"]):
        intent = "log_sale"
        qty = parse_egyptian_quantities(query)
        price = extract_price(query)

        # Match known medication
        item_name = "دواء مبيع"
        for alias, canonical_name in MEDICINE_ALIASES:
            if alias.lower() in query_lower:
                item_name = canonical_name
                break

        # If price wasn't specified in chat, we default to catalog price or 35 EGP
        if price == 0.0:
            default_prices = {
                "بنادول اكسترا (أحمر)": 35.0,
                "بنادول أزرق (عادي)": 28.0,
                "أوجمنتين 1 جم أقراص": 115.0,
                "كونجستال أقراص للبرد": 31.0,
                "بروفين 400 مجم": 42.0,
                "كيتوفان 50 مجم": 27.0,
                "فلاجيل 500 مجم": 24.0,
                "أنتينال كبسول للمغص والإسهال": 34.0,
                "أوتريفين بخاخ أنف للكبار": 22.0,
            }
            price = default_prices.get(item_name, 35.0)

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

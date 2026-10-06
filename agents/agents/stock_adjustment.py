# agents/agents/stock_adjustment.py
"""The "adjust this product's stock?" card (Session 126). Pure Python, stdlib only.

Nothing changes until a person confirms. The card holds the product, the stock now, the
stock after and the reason. The caller passes either `new_stock` ("make it 15") or
`change` ("add 10" / "remove 3"); the difference is worked out here, never by the model.
A decrease needs a reason (stocktake, damaged, expired...).
"""
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

MAX_STOCK = 1_000_000


def _q(value) -> float:
    return round(float(value), 4)


def clean_reason(raw) -> str:
    return " ".join(str(raw or "").split())[:200]


def build_stock_adjustment_proposal(
    current: dict,
    new_stock: Optional[float] = None,
    change: Optional[float] = None,
    reason=None,
    language: str = "ar",
) -> Optional[dict]:
    """The card, or None when: not exactly one of new_stock/change, the result is negative or
    above the limit, nothing would change, or stock goes down with no reason."""
    if (new_stock is None) == (change is None) or current.get("id") is None:
        return None
    before = _q(current.get("stock_qty") or 0.0)
    try:
        after = _q(new_stock) if new_stock is not None else _q(before + float(change))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(after) or after < 0 or after > MAX_STOCK:
        return None
    delta = _q(after - before)
    if delta == 0:
        return None
    reason_text = clean_reason(reason)
    if delta < 0 and not reason_text:
        return None

    is_ar = language != "en"
    warnings = []
    if delta < 0:
        warnings.append(
            "Stock goes down without a sale: no money is recorded, only the audit log keeps this."
            if not is_ar else "سينقص المخزون بدون عملية بيع: لا يُسجَّل أي مبلغ، والسجل فقط يحفظ هذا التعديل."
        )
    else:
        warnings.append(
            "This adds stock without recording a purchase or an amount owed. For goods bought from a supplier, use a restock."
            if not is_ar else "هذا يضيف مخزونًا بدون تسجيل شراء أو مبلغ مستحق. للبضاعة المشتراة من مورد استخدم التوريد."
        )
        if float(current.get("unit_buy_price") or 0.0) <= 0:
            warnings.append(
                "The product has no buy price, so the added units have unknown cost and profit stays incomplete."
                if not is_ar else "لا يوجد سعر شراء للمنتج، لذلك تكلفة الوحدات المضافة غير معروفة ولن يكتمل حساب الربح."
            )
    if after == 0:
        warnings.append("The product will be out of stock." if not is_ar else "سينفد المنتج من المخزون.")

    name_ar = str(current.get("name_ar") or "")
    name_en = str(current.get("name_en") or "") or name_ar
    name = name_ar if is_ar else name_en
    return {
        "id": f"prop-{uuid.uuid4().hex}",
        "action_type": "adjust_stock",
        "title": "تعديل المخزون" if is_ar else "Adjust Stock",
        "summary_ar": f"تعديل مخزون {name_ar} من {before:g} إلى {after:g} ({delta:+g})",
        "summary_en": f"Set stock of {name_en} from {before:g} to {after:g} ({delta:+g})",
        "items": [],
        "total_amount": 0.0,
        "payment_method": "cash",
        "status": "pending_confirmation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "warnings": warnings,
        "target_item_id": int(current["id"]),
        "adjustment": {
            "item_name": name,
            "stock_before": before,
            "stock_after": after,
            "stock_change": delta,
            "reason": reason_text or None,
        },
    }
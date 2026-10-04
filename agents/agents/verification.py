# agents/agents/verification.py
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List
from agents.state import AgentState


def verification_agent(state: AgentState) -> AgentState:
    """
    Verification & Human-In-The-Loop Agent.
    Strictly validates inventory presence and stock availability before surfacing proposals.
    Never creates a sale proposal for non-existent items or overdrafted stock (Requirements 8 & 9).
    """
    intent = state.get("intent")
    extracted_items = state.get("extracted_items", [])
    total_amount = state.get("total_amount", 0.0)
    payment_method = state.get("payment_method", "cash")
    lang = state.get("language", "ar")
    is_ar = lang != "en"

    # If inventory data is available, attach stock counts and validate
    inventory_items = state.get("inventory_data", [])
    inv_map = {item["name_ar"].strip().casefold(): item for item in inventory_items}
    inv_map_en = {item.get("name_en", "").strip().casefold(): item for item in inventory_items}

    def exact_inventory_match(name: str):
        key = name.strip().casefold()
        return inv_map.get(key) or inv_map_en.get(key)

    sale_batches_remaining: dict[int, list[list[float]]] = {}

    def fifo_sale_price(matched_item: dict, quantity: float) -> float:
        """Price consecutive sale lines from oldest lots without reusing stock."""
        item_id = int(matched_item["id"])
        batches = sale_batches_remaining.setdefault(
            item_id,
            [
                [max(0.0, float(batch.get("quantity", 0))), float(batch.get("unit_sell_price", 0))]
                for batch in matched_item.get("price_batches", [])
            ],
        )
        remaining = quantity
        total = 0.0
        for batch in batches:
            take = min(batch[0], remaining)
            total += take * batch[1]
            batch[0] -= take
            remaining -= take
            if remaining <= 0:
                break
        # Legacy or manually adjusted stock may not yet have a matching lot.
        if remaining > 0:
            total += remaining * float(matched_item.get("unit_sell_price", 0))
        return total / quantity if quantity > 0 else 0.0

    # Quantity already requested per product on earlier lines of this same sale.
    requested_so_far: dict[int, float] = {}

    # Strict Validation for Sales
    if intent in {"log_sale", "log_restock"}:
        for it in extracted_items:
            item_name = it["item_name"]
            matched_item = exact_inventory_match(item_name)

            # 1. Product NOT in inventory -> REJECT SALE PROPOSAL (Requirement 8)
            if not matched_item:
                if is_ar:
                    rejection_text = (
                        f"❌ لا يمكن إتمام هذه العملية.\n\n"
                        f"السبب:\n"
                        f"الصنف المطلوب ({item_name}) غير مسجل في مخزون الصيدلية.\n\n"
                        f"ما يجب عليك فعله:\n"
                        f"1. إضافة المنتج من صفحة المخزون باستخدام الإدخال اليدوي.\n"
                        f"2. التحقق من الاسم والباركود وسعر البيع.\n"
                        f"3. العودة وتسجيل حركة البيع مجدداً."
                    )
                else:
                    rejection_text = (
                        f"❌ This action cannot be processed.\n\n"
                        f"Reason:\n"
                        f"The requested product ({item_name}) was not found in the pharmacy inventory.\n\n"
                        f"What you need to do:\n"
                        f"1. Add the product using the manual inventory form. Image extraction is currently unavailable.\n"
                        f"2. Verify its name, barcode, and sell price.\n"
                        f"3. Return and submit the sale again."
                    )
                return {
                    **state,
                    "proposal": None,
                    "answer_text": rejection_text,
                }

            # Sales with insufficient stock are stopped before a proposal is shown.
            # The same product on two lines counts together, as confirmation checks it.
            total_requested = it["quantity"]
            if intent == "log_sale":
                earlier = requested_so_far.get(matched_item["id"])
                if earlier is not None:
                    total_requested += earlier
                requested_so_far[matched_item["id"]] = total_requested
            if intent == "log_sale" and total_requested > matched_item["stock_qty"]:
                if is_ar:
                    rejection_text = (
                        f"⚠️ لا يمكن إتمام عملية البيع.\n\n"
                        f"السبب:\n"
                        f"الكمية المطلوبة ({total_requested}) أكبر من الرصيد المتوفر حالياً في الصيدلية ({matched_item['stock_qty']} علبة) للدواء '{matched_item['name_ar']}'.\n\n"
                        f"ما يجب عليك فعله:\n"
                        f"1. تعديل الكمية المطلوبة لتناسب الرصيد المتبقي.\n"
                        f"2. أو تسجيل فاتورة توريد (Restock) لزيادة رصيد الصنف أولاً."
                    )
                else:
                    rejection_text = (
                        f"⚠️ This sale cannot be processed.\n\n"
                        f"Reason:\n"
                        f"The requested quantity ({total_requested}) exceeds available stock ({matched_item['stock_qty']} packs) for '{matched_item.get('name_en', matched_item['name_ar'])}'.\n\n"
                        f"What you need to do:\n"
                        f"1. Adjust the quantity to match available stock.\n"
                        f"2. Or log a restock first to increase inventory balance."
                    )
                return {
                    **state,
                    "proposal": None,
                    "answer_text": rejection_text,
                }

    # If validation passed, format proposed items
    formatted_items = []
    warnings: List[str] = []
    for it in extracted_items:
        item_copy = dict(it)
        matched_item = exact_inventory_match(it["item_name"])
        if matched_item:
            item_copy["matched_inventory_id"] = matched_item["id"]
            item_copy["stock_available"] = matched_item["stock_qty"]
            # Use the catalog's transaction-appropriate price when none was specified.
            if item_copy.get("unit_price", 0.0) <= 0.0:
                if intent == "log_sale":
                    item_copy["unit_price"] = fifo_sale_price(matched_item, item_copy["quantity"])
                else:
                    price_field = "unit_buy_price" if intent == "log_restock" else "unit_sell_price"
                    item_copy["unit_price"] = matched_item[price_field]
        item_copy["subtotal"] = item_copy["quantity"] * item_copy.get("unit_price", 0.0)
        formatted_items.append(item_copy)

    total_amount = sum(it["quantity"] * it.get("unit_price", 0.0) for it in formatted_items)

    # The id becomes the global primary key of the pending action and, once confirmed,
    # of the ledger entry. A 10-hex-digit id (40 bits) would collide at scale across pharmacies.
    proposal_id = f"prop-{uuid.uuid4().hex}"
    now_iso = datetime.now(timezone.utc).isoformat()

    if intent == "log_sale":
        title = "تسجيل عملية بيع" if is_ar else "Log Sale Action"
        summary_ar = f"تسجيل بيع {len(formatted_items)} أصناف بقيمة إجمالية {total_amount:.2f} ج.م"
        summary_en = f"Log sale of {len(formatted_items)} items for total {total_amount:.2f} EGP"
        answer_text = (
            f"تمام يا دكتور، جهزتلك عملية البيع بإجمالي {total_amount:.2f} ج.م. راجع الأصناف واضغط 'تأكيد وحفظ' أو عدل عليها:"
            if is_ar else
            f"Ready! Sale proposal prepared for {total_amount:.2f} EGP. Please review items and press Confirm:"
        )
    elif intent == "log_expense":
        title = "تسجيل مصروفات" if is_ar else "Log Expense"
        exp_name = formatted_items[0]["item_name"] if formatted_items else ("مصروفات" if is_ar else "Expense")
        summary_ar = f"تسجيل {exp_name} بقيمة {total_amount:.2f} ج.م ({payment_method})"
        summary_en = f"Log expense '{exp_name}' for {total_amount:.2f} EGP"
        answer_text = (
            f"سجلتلك المصروفات للمراجعة قبل الحفظ في الخزينة:"
            if is_ar else
            f"Expense proposal prepared for review before committing to ledger:"
        )
    elif intent == "log_restock":
        title = "تسجيل توريد مخزن" if is_ar else "Log Restock"
        summary_ar = f"إضافة بضاعة للمخزن بقيمة {total_amount:.2f} ج.م"
        summary_en = f"Restock inventory for {total_amount:.2f} EGP"
        answer_text = (
            f"وصلت البضاعة؟ راجع الكميات وأسعار الشراء لتحديث المخزن:"
            if is_ar else
            f"Shipment received? Please review restock quantities and costs:"
        )
    else:
        return state

    proposal = {
        "id": proposal_id,
        "action_type": intent,
        "title": title,
        "summary_ar": summary_ar,
        "summary_en": summary_en,
        "items": formatted_items,
        "total_amount": total_amount,
        "payment_method": payment_method,
        "status": "pending_confirmation",
        "created_at": now_iso,
        "warnings": warnings,
    }

    return {
        **state,
        "proposal": proposal,
        "answer_text": answer_text,
    }
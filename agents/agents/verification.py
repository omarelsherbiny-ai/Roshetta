# agents/agents/verification.py
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from decimal import Decimal, ROUND_HALF_UP
from typing import List
from agents.state import AgentState


def _round2(value) -> float:
    """Round half-up to 2 places on the decimal text of the number.

    Same rule as ``round_money`` in ``server/app/db/money.py`` (this layer stays plain
    Python, so the rule is repeated here; ``tests/test_proposal_money.py`` checks that
    the two never differ). Python's own ``round`` would turn 10.005 into 10.0.
    A non-finite value is returned unchanged so confirmation rejects it as before.
    """
    number = Decimal(str(value))
    if not number.is_finite():
        return float(number)
    return float(number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _sum2(values) -> float:
    """Exact sum of 2-place values, rounded to 2 places (no float drift)."""
    total = Decimal(0)
    for value in values:
        total += Decimal(str(value))
    return _round2(total)


def _similar_products(name: str, inventory_items: list) -> list:
    """Existing products that look like `name`: exact name first, then close spellings.

    Same-pharmacy inventory only (the caller passes only what this member may view).
    A close spelling is a ratio of at least 0.8 against the whole name or any one word
    of it, or one name containing the other (4+ letters), so "pandol" finds "Panadol".
    """
    key = name.strip().casefold()
    found = []
    for item in inventory_items:
        exact = False
        close = False
        for field in ("name_ar", "name_en"):
            other = (item.get(field) or "").strip().casefold()
            if not other:
                continue
            if other == key:
                exact = True
                break
            candidates = [other] + other.split()
            if any(SequenceMatcher(None, key, c).ratio() >= 0.8 for c in candidates):
                close = True
            elif len(key) >= 4 and (key in other or (len(other) >= 4 and other in key)):
                close = True
        if exact or close:
            found.append({
                "id": item.get("id"),
                "name_ar": item.get("name_ar") or "",
                "name_en": item.get("name_en") or "",
                "stock_qty": float(item.get("stock_qty") or 0.0),
                "unit_sell_price": float(item.get("unit_sell_price") or 0.0),
                "exact": exact,
            })
    found.sort(key=lambda row: not row["exact"])
    return found[:3]


def _create_product_proposal(state: AgentState) -> AgentState:
    """Builds the "add this product?" card. Nothing is created until the person confirms."""
    is_ar = state.get("language", "ar") != "en"
    draft = state.get("product_draft") or {}
    name = (draft.get("name") or "").strip()
    buy = draft.get("unit_buy_price")
    sell = draft.get("unit_sell_price")
    qty = draft.get("stock_qty")

    if not name or sell is None or sell <= 0:
        text = (
            "محتاج اسم المنتج وسعر البيع عشان أجهز بطاقة الإضافة. مثال: أضف منتج بنادول سعر الشراء 10 سعر البيع 15"
            if is_ar else
            "I need the product name and its sell price to prepare the card. Example: add product Panadol buy 10 sell 15"
        )
        return {**state, "proposal": None, "answer_text": text}

    buy = _round2(buy or 0.0)
    sell = _round2(sell)
    qty = float(qty) if qty is not None else 0.0
    duplicates = _similar_products(name, state.get("inventory_data") or [])

    warnings: List[str] = []
    if any(row["exact"] for row in duplicates):
        warnings.append("A product with this name already exists." if not is_ar else "يوجد منتج بنفس الاسم بالفعل.")
    elif duplicates:
        shown = duplicates[0]["name_en"] or duplicates[0]["name_ar"]
        warnings.append(f"A similar product exists: {shown}." if not is_ar else f"يوجد منتج مشابه: {duplicates[0]['name_ar'] or shown}.")
    if buy <= 0:
        warnings.append(
            "No buy price was given, so profit for this product will be incomplete."
            if not is_ar else "لم يتم تحديد سعر الشراء، لذلك لن يكتمل حساب الربح لهذا المنتج."
        )
    elif sell < buy:
        warnings.append("The sell price is lower than the buy price." if not is_ar else "سعر البيع أقل من سعر الشراء.")

    # Category: warn when none was given, or when no product uses it yet (confirming
    # creates the category row if it does not exist). Known categories come from the
    # catalog the caller passed in (same pharmacy only).
    category = (draft.get("category") or "").strip() or None
    known_categories = {(it.get("category") or "").strip().casefold() for it in (state.get("inventory_data") or [])}
    known_categories.discard("")
    if category is None:
        warnings.append("No category was given." if not is_ar else "لم يتم تحديد القسم.")
    elif category.casefold() not in known_categories:
        warnings.append(
            f"No product uses the category '{category}' yet; it will be created if it does not exist."
            if not is_ar else f"لا يوجد منتج في القسم '{category}' بعد؛ سيتم إنشاؤه إن لم يكن موجودًا."
        )

    product = {
        "name_ar": name,
        "name_en": name,
        "unit_buy_price": buy,
        "unit_sell_price": sell,
        "stock_qty": qty,
        "min_threshold": float(draft.get("min_threshold") or 5.0),
        "category": category,
    }
    proposal = {
        "id": f"prop-{uuid.uuid4().hex}",
        "action_type": "create_product",
        "title": "إضافة منتج جديد" if is_ar else "Add New Product",
        "summary_ar": f"إضافة المنتج {name} (شراء {buy:.2f} / بيع {sell:.2f} ج.م)",
        "summary_en": f"Add product {name} (buy {buy:.2f} / sell {sell:.2f} EGP)",
        "items": [],
        "total_amount": 0.0,
        "payment_method": "cash",
        "status": "pending_confirmation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "warnings": warnings,
        "product": product,
        "duplicates": duplicates,
    }
    answer_text = (
        f"جهزتلك بطاقة إضافة المنتج '{name}'. راجع البيانات واضغط 'تأكيد وإضافة':"
        if is_ar else
        f"Ready! Review the details for new product '{name}' and press Confirm and add:"
    )
    return {**state, "proposal": proposal, "answer_text": answer_text}


def clean_category_name(raw) -> str:
    """Inner whitespace collapsed, at most 40 characters ('' when blank)."""
    return " ".join(str(raw or "").split())[:40]


def build_category_proposal(name, language: str = "ar"):
    """The "create this category?" card, or None when the name is blank.

    Pure Python, like the product card: nothing is created until a person confirms.
    The card carries no line items (items is an empty list) and the name in
    `category_name`, which the person may edit before confirming.
    """
    clean = clean_category_name(name)
    if not clean:
        return None
    is_ar = language != "en"
    return {
        "id": f"prop-{uuid.uuid4().hex}",
        "action_type": "create_category",
        "title": "إضافة قسم جديد" if is_ar else "Add New Category",
        "summary_ar": f"إنشاء القسم {clean}",
        "summary_en": f"Create category {clean}",
        "items": [],
        "total_amount": 0.0,
        "payment_method": "cash",
        "status": "pending_confirmation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "warnings": [],
        "category_name": clean,
    }


def build_stock_reduction_proposal(current: dict, new_quantity, reason=None, language: str = "ar"):
    """The "set this product's stock lower?" card, or None when the new count is not lower.

    Pure Python and read-only: nothing changes until a person confirms. `current` is the
    product as stored (id, name_ar, name_en, stock_qty). Only a DECREASE is ever carded
    (damaged or expired units, a recount): more stock comes in through a restock, which
    records what it cost. The card carries no line items and no money; `stock_change`
    holds the count now (`before`), the count after (`after`) and the difference.
    """
    try:
        before = float(current.get("stock_qty") or 0.0)
        after = float(new_quantity)
    except (TypeError, ValueError):
        return None
    if not (after == after and before == before) or after < 0 or after >= before:
        return None
    is_ar = language != "en"
    name_ar = str(current.get("name_ar") or "")
    name_en = str(current.get("name_en") or "") or name_ar
    difference = before - after
    clean_reason = " ".join(str(reason or "").split())[:100] or None
    return {
        "id": f"prop-{uuid.uuid4().hex}",
        "action_type": "reduce_stock",
        "title": "تعديل المخزون" if is_ar else "Reduce Stock",
        "summary_ar": f"تقليل رصيد {name_ar} من {before:g} إلى {after:g}",
        "summary_en": f"Reduce {name_en} stock from {before:g} to {after:g}",
        "items": [],
        "total_amount": 0.0,
        "payment_method": "cash",
        "status": "pending_confirmation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "warnings": [
            "هذا التعديل لا يسجل بيعًا ولا مصروفًا." if is_ar
            else "This is a stock correction: it records no sale and no expense."
        ],
        "target_item_id": int(current["id"]),
        "stock_change": {
            "item_name": name_ar if is_ar else name_en,
            "before": before,
            "after": after,
            "difference": difference,
            "reason": clean_reason,
        },
    }


UPDATE_EDITABLE_FIELDS = ("name_ar", "name_en", "unit_buy_price", "unit_sell_price", "min_threshold", "category")


def _update_value(field: str, value):
    """One requested change, normalised the way the confirm will store it."""
    if field in ("name_ar", "name_en"):
        return str(value).strip()
    if field == "category":
        return clean_category_name(value)
    if field in ("unit_buy_price", "unit_sell_price"):
        return _round2(value)
    return float(value)


def build_product_update_proposal(current: dict, changes: dict, language: str = "ar", others: list | None = None):
    """The "update this product?" card, or None when no requested value differs from the product.

    Pure Python and read-only: nothing is changed until a person confirms. `current` is the
    product as stored (id, name_ar, name_en, unit_buy_price, unit_sell_price, stock_qty,
    min_threshold, category); `changes` holds only the values the user asked to change;
    `others` is the rest of the pharmacy's catalog (for a same-name warning). The card keeps
    the full proposed product in `product`, the values it had in `before`, the product id in
    `target_item_id` and the fields that differ in `changed_fields`. Stock is never part of
    an update (it changes only through a confirmed stock movement).
    """
    is_ar = language != "en"
    before = {
        "name_ar": str(current.get("name_ar") or ""),
        "name_en": str(current.get("name_en") or ""),
        "unit_buy_price": _round2(current.get("unit_buy_price") or 0.0),
        "unit_sell_price": _round2(current.get("unit_sell_price") or 0.0),
        "stock_qty": float(current.get("stock_qty") or 0.0),
        "min_threshold": float(current.get("min_threshold") or 5.0),
        "category": (current.get("category") or None),
    }
    proposed = dict(before)
    changed = []
    for field in UPDATE_EDITABLE_FIELDS:
        if changes.get(field) is None:
            continue
        value = _update_value(field, changes[field])
        if field == "category" and value == "":
            continue
        if field in ("name_ar", "name_en") and not value:
            continue
        if value != before[field]:
            proposed[field] = value
            changed.append(field)
    if not changed or current.get("id") is None:
        return None

    warnings: List[str] = []
    buy, sell = proposed["unit_buy_price"], proposed["unit_sell_price"]
    if sell <= 0:
        return None
    if buy > 0 and sell < buy:
        warnings.append("The sell price is lower than the buy price." if not is_ar else "سعر البيع أقل من سعر الشراء.")
    if "unit_sell_price" in changed:
        warnings.append(
            "Stock already in the pharmacy keeps the sell price it was bought with; the new price applies to the next stock you add."
            if not is_ar else
            "المخزون الموجود حاليًا يحتفظ بسعر البيع القديم؛ السعر الجديد يسري على الكميات التي تضيفها لاحقًا."
        )
    if "name_ar" in changed or "name_en" in changed:
        taken = {
            (other.get(f) or "").strip().casefold()
            for other in (others or []) if other.get("id") != current.get("id")
            for f in ("name_ar", "name_en")
        }
        taken.discard("")
        if any(proposed[f].casefold() in taken for f in ("name_ar", "name_en") if f in changed):
            warnings.append("Another product already has this name." if not is_ar else "يوجد منتج آخر بنفس الاسم.")
    if "category" in changed:
        known = {(other.get("category") or "").strip().casefold() for other in (others or [])}
        known.discard("")
        if proposed["category"].casefold() not in known:
            warnings.append(
                f"No product uses the category '{proposed['category']}' yet; it will be created if it does not exist."
                if not is_ar else f"لا يوجد منتج في القسم '{proposed['category']}' بعد؛ سيتم إنشاؤه إن لم يكن موجودًا."
            )

    labels_en = {"name_ar": "Arabic name", "name_en": "English name", "unit_buy_price": "buy price",
                 "unit_sell_price": "sell price", "min_threshold": "low-stock level", "category": "category"}
    labels_ar = {"name_ar": "الاسم العربي", "name_en": "الاسم الإنجليزي", "unit_buy_price": "سعر الشراء",
                 "unit_sell_price": "سعر البيع", "min_threshold": "حد التنبيه", "category": "القسم"}

    def shown(field, value):
        if field in ("unit_buy_price", "unit_sell_price"):
            return f"{value:.2f}"
        if field == "min_threshold":
            return f"{value:g}"
        return str(value) if value else "-"

    parts_en = [f"{labels_en[f]} {shown(f, before[f])} -> {shown(f, proposed[f])}" for f in changed]
    parts_ar = [f"{labels_ar[f]} {shown(f, before[f])} ← {shown(f, proposed[f])}" for f in changed]
    name = before["name_ar"] if is_ar else (before["name_en"] or before["name_ar"])
    product = {k: proposed[k] for k in ("name_ar", "name_en", "unit_buy_price", "unit_sell_price", "stock_qty", "min_threshold", "category")}
    return {
        "id": f"prop-{uuid.uuid4().hex}",
        "action_type": "update_product",
        "title": "تعديل منتج" if is_ar else "Update Product",
        "summary_ar": f"تعديل المنتج {name}: " + "، ".join(parts_ar),
        "summary_en": f"Update product {name}: " + ", ".join(parts_en),
        "items": [],
        "total_amount": 0.0,
        "payment_method": "cash",
        "status": "pending_confirmation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "warnings": warnings,
        "product": product,
        "before": before,
        "target_item_id": int(current["id"]),
        "changed_fields": changed,
    }


def build_invite_proposal(role: dict, expires_in_days: int = 7, max_uses: int = 1, language: str = "ar"):
    """The "create this invitation link?" card, or None when the role or the numbers are invalid.

    Pure Python. The card holds the role and the settings only: the link itself does not exist
    until a person confirms (it is a credential, so it never passes through the assistant and
    is never stored on the card). `role`: {"name", "kind", "fixed_role", "custom_role_id",
    "scopes"}. Days are 1 to 30, uses 1 to 50.
    """
    try:
        days, uses = int(expires_in_days), int(max_uses)
    except (TypeError, ValueError):
        return None
    name = str(role.get("name") or "").strip()
    fixed, custom_id = role.get("fixed_role"), role.get("custom_role_id")
    if not name or (fixed is None) == (custom_id is None) or not 1 <= days <= 30 or not 1 <= uses <= 50:
        return None
    is_ar = language != "en"
    warnings: List[str] = []
    if "manage_staff" in (role.get("scopes") or []):
        warnings.append("This role can invite and manage other members." if not is_ar else "هذا الدور يمكنه دعوة وإدارة أعضاء آخرين.")
    if uses > 1:
        warnings.append(
            f"The link can be used by {uses} people." if not is_ar else f"يمكن استخدام الرابط من {uses} أشخاص."
        )
    return {
        "id": f"prop-{uuid.uuid4().hex}",
        "action_type": "create_invite",
        "title": "دعوة عضو جديد" if is_ar else "Invite a Member",
        "summary_ar": f"إنشاء رابط دعوة بدور {name} صالح {days} يومًا",
        "summary_en": f"Create an invitation link for the role {name}, valid {days} days",
        "items": [],
        "total_amount": 0.0,
        "payment_method": "cash",
        "status": "pending_confirmation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "warnings": warnings,
        "invite": {
            "role_name": name,
            "kind": role.get("kind") or ("custom" if custom_id is not None else "built_in"),
            "fixed_role": fixed,
            "custom_role_id": custom_id,
            "expires_in_days": days,
            "max_uses": uses,
        },
    }


def verification_agent(state: AgentState) -> AgentState:
    """
    Verification & Human-In-The-Loop Agent.
    Strictly validates inventory presence and stock availability before surfacing proposals.
    Never creates a sale proposal for non-existent items or overdrafted stock (Requirements 8 & 9).
    """
    intent = state.get("intent")
    if intent == "create_product":
        return _create_product_proposal(state)
    extracted_items = state.get("extracted_items", [])
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

    def resolve_inventory_match(name: str):
        """Exact name first; else the one close spelling, never a guess between several.

        Returns (item or None, close candidates). The card shows the resolved real name and
        a person still confirms it, so a close spelling ("panadol" for "Panadol Extra")
        is accepted only when it is the single candidate.
        """
        exact = exact_inventory_match(name)
        if exact:
            return exact, []
        close = _similar_products(name, inventory_items) if name.strip() else []
        if len(close) == 1:
            by_id = {item.get("id"): item for item in inventory_items}
            return by_id.get(close[0]["id"]), close
        return None, close

    # Own copies: a resolved name is written back so later steps match it exactly.
    extracted_items = [dict(it) for it in extracted_items]

    # Strict Validation for Sales
    if intent in {"log_sale", "log_restock"}:
        for it in extracted_items:
            item_name = it["item_name"]
            if not item_name.strip():
                ask = (
                    "أي منتج تقصد؟ اكتب اسم المنتج مع الكمية، مثال: بعت 3 بنادول"
                    if is_ar else
                    "Which product do you mean? Type the product name with the quantity, for example: sold 3 Panadol"
                )
                return {**state, "proposal": None, "answer_text": ask}
            matched_item, close_candidates = resolve_inventory_match(item_name)
            if matched_item:
                it["item_name"] = matched_item["name_ar"]

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
                if close_candidates:
                    names = "، ".join((c["name_ar"] or c["name_en"]) for c in close_candidates) if is_ar else ", ".join((c["name_en"] or c["name_ar"]) for c in close_candidates)
                    rejection_text += (f"\n\nهل تقصد: {names}؟ اكتب الاسم كما هو في المخزون." if is_ar else f"\n\nDid you mean: {names}? Type the name as it appears in the inventory.")
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
        # Money is shown exactly as confirmation will book it (Waiting item 108):
        # the unit price to 2 places first (the confirm request does the same), then
        # the line subtotal from that rounded price.
        item_copy["unit_price"] = _round2(item_copy.get("unit_price", 0.0))
        item_copy["subtotal"] = _round2(item_copy["quantity"] * item_copy["unit_price"])
        formatted_items.append(item_copy)

    # The total is the sum of the rounded line subtotals, as confirmation computes it.
    total_amount = _sum2(it["subtotal"] for it in formatted_items)

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
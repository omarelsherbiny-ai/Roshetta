# agents/agents/inventory.py
from agents.state import AgentState


def inventory_agent(state: AgentState) -> AgentState:
    """
    Inventory Agent.
    Monitors stock levels, detects shortages, and suggests generic alternatives.
    """
    inv_data = state.get("inventory_data", [])
    is_english = state.get("language") == "en"
    
    # Filter low stock items
    low_stock = [item for item in inv_data if item.get("stock_qty", 0) <= item.get("min_threshold", 5)]

    if not inv_data:
        answer = (
            "No inventory products are recorded for this pharmacy yet."
            if is_english else "لا توجد أصناف مسجلة في مخزون هذه الصيدلية حتى الآن."
        )
    elif not low_stock:
        answer = (
            "No recorded products are at or below their low-stock threshold."
            if is_english else "لا توجد أصناف مسجلة عند حد المخزون المنخفض أو دونه."
        )
    else:
        lines = [
            "⚠️ Products at or below their low-stock threshold:\n"
            if is_english else "⚠️ أصناف عند حد المخزون المنخفض أو قريبة من النفاد:\n"
        ]
        for item in low_stock:
            name = item.get("name_en") if is_english else item.get("name_ar")
            name = name or item.get("name_ar") or item.get("name_en") or ""
            unit = "units" if is_english else "وحدة"
            current = item.get("stock_qty", 0)
            threshold = item.get("min_threshold", 5)
            current_text = f"{float(current):g}"
            threshold_text = f"{float(threshold):g}"
            lines.append(
                f"• {name} ({'current stock' if is_english else 'الرصيد الحالي'}: {current_text} {unit} / "
                f"{'threshold' if is_english else 'حد التنبيه'}: {threshold_text})"
            )
        lines.append(
            "\nReview these items before preparing a restock."
            if is_english else "\nراجع هذه الأصناف قبل تسجيل أي توريد."
        )
        answer = "\n".join(lines)

    return {
        **state,
        "answer_text": answer,
    }
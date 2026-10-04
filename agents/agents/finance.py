from agents.state import AgentState


def finance_agent(state: AgentState) -> AgentState:
    """
    Sales and Finance Agent.
    Grounded strictly in real database ledger numbers, zero hallucinations.
    """
    fin_data = state.get("financial_data") or {
        "total_sales": 0.0,
        "total_expenses": 0.0,
        "net_profit": None,
        "profit_complete": False,
        "sales_count": 0,
        "expenses_count": 0
    }

    sales = fin_data["total_sales"]
    expenses = fin_data["total_expenses"]
    profit = fin_data.get("net_profit")
    profit_complete = fin_data.get("profit_complete", False)
    sales_cnt = fin_data["sales_count"]
    exp_cnt = fin_data["expenses_count"]

    if state.get("language") == "en":
        profit_line = (
            f"• Net profit after product cost and expenses: {profit:,.2f} EGP\n"
            if profit_complete and profit is not None
            else "• Net profit is unavailable because cost data is missing for one or more sales.\n"
        )
        answer = (
            "📊 Today's financial summary:\n\n"
            f"• Sales: {sales:,.2f} EGP ({sales_cnt} sales)\n"
            f"• Expenses: {expenses:,.2f} EGP ({exp_cnt} expenses)\n"
            f"{profit_line}\n"
            "Figures come from today's recorded ledger entries."
        )
    else:
        profit_line = (
            f"• صافي الربح بعد تكلفة البضاعة والمصروفات: {profit:,.2f} ج.م\n"
            if profit_complete and profit is not None
            else "• صافي الربح غير متاح لوجود تكلفة شراء غير مسجلة لبعض المبيعات.\n"
        )
        answer = (
            "📊 ملخص الحسابات لليوم:\n\n"
            f"• إجمالي المبيعات: {sales:,.2f} ج.م ({sales_cnt} عملية بيع)\n"
            f"• إجمالي المصروفات: {expenses:,.2f} ج.م ({exp_cnt} مصروف)\n"
            f"{profit_line}\n"
            "الأرقام محسوبة من الحركات المسجلة اليوم."
        )

    return {
        **state,
        "answer_text": answer,
    }

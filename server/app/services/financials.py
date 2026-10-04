from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.db.models import LedgerEntry, LedgerEntryItem


BUSINESS_TIMEZONE = ZoneInfo("Africa/Cairo")


def local_day_bounds_utc(day: date | None = None) -> tuple[datetime, datetime, str]:
    local_day = day or datetime.now(BUSINESS_TIMEZONE).date()
    start_local = datetime.combine(local_day, time.min, tzinfo=BUSINESS_TIMEZONE)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc, local_day.isoformat()


async def daily_financial_summary(
    db: AsyncSession,
    pharmacy_id: int,
    day: date | None = None,
    user_id: int | None = None,
) -> dict:
    return await financial_summary_for_range(
        db,
        pharmacy_id,
        start_day=day,
        end_day=day,
        user_id=user_id,
    )


async def financial_summary_for_range(
    db: AsyncSession,
    pharmacy_id: int,
    start_day: date | None = None,
    end_day: date | None = None,
    user_id: int | None = None,
) -> dict:
    today = datetime.now(BUSINESS_TIMEZONE).date()
    start_day = start_day or end_day or today
    end_day = end_day or start_day
    if end_day < start_day:
        raise ValueError("Report end date cannot be earlier than its start date.")
    start_utc, _, start_label = local_day_bounds_utc(start_day)
    _, end_utc, end_label = local_day_bounds_utc(end_day)
    date_label = start_label if start_day == end_day else f"{start_label} – {end_label}"
    entry_scope = [
        LedgerEntry.pharmacy_id == pharmacy_id,
        LedgerEntry.created_at >= start_utc,
        LedgerEntry.created_at < end_utc,
    ]
    if user_id is not None:
        entry_scope.append(func.coalesce(LedgerEntry.confirmed_by, LedgerEntry.created_by) == user_id)
    totals = await db.execute(
        select(
            LedgerEntry.entry_type,
            func.coalesce(func.sum(LedgerEntry.total_amount), 0.0),
            func.count(LedgerEntry.id),
        )
        .where(*entry_scope, LedgerEntry.entry_type.in_(("log_sale", "log_expense")))
        .group_by(LedgerEntry.entry_type)
    )
    by_type = {row[0]: (float(row[1]), int(row[2])) for row in totals.all()}
    sales_total, sales_count = by_type.get("log_sale", (0.0, 0))
    expenses_total, expenses_count = by_type.get("log_expense", (0.0, 0))

    sale_entries = await db.execute(
        select(LedgerEntry.id, LedgerEntryItem.quantity, LedgerEntryItem.unit_cost)
        .select_from(LedgerEntry)
        .join(LedgerEntryItem, LedgerEntryItem.entry_id == LedgerEntry.id)
        .where(*entry_scope, LedgerEntry.entry_type == "log_sale")
    )
    rows = sale_entries.all()
    sale_entry_ids = await db.execute(
        select(LedgerEntry.id).where(*entry_scope, LedgerEntry.entry_type == "log_sale")
    )
    missing_cost = {row[0] for row in sale_entry_ids.all()} - {row[0] for row in rows}
    cost_complete = not missing_cost and all(row[2] is not None for row in rows)
    cost_of_goods = sum(float(quantity) * float(unit_cost) for _, quantity, unit_cost in rows if unit_cost is not None)
    gross_profit = sales_total - cost_of_goods if cost_complete else None
    net_profit = gross_profit - expenses_total if gross_profit is not None else None

    return {
        "date": date_label,
        "total_sales": sales_total,
        "total_expenses": expenses_total,
        "cost_of_goods": cost_of_goods if cost_complete else None,
        "gross_profit": gross_profit,
        "net_profit": net_profit,
        "profit_complete": cost_complete,
        "sales_count": sales_count,
        "expenses_count": expenses_count,
    }

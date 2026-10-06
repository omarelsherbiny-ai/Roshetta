# server/app/api/ledger.py
import json
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import Float, and_, func, literal, or_, text

from server.app.db.session import get_db
from server.app.db.models import AuditLog, LedgerEntry, RestockSettlement, User, has_permission
from server.app.db.money import MoneyIn, money_sum, round_money
from server.app.services.clock import utc_now_naive
from server.app.services.rbac import get_current_user, require_permission
from server.app.services.financials import daily_financial_summary, financial_summary_for_range, local_day_bounds_utc

router = APIRouter(prefix="/api/ledger", tags=["Ledger"])


class FinancialSummaryResponse(BaseModel):
    date: str
    total_sales: float
    total_expenses: float
    cost_of_goods: Optional[float]
    gross_profit: Optional[float]
    net_profit: Optional[float]
    profit_complete: bool
    sales_count: int
    expenses_count: int


class LedgerLineResponse(BaseModel):
    item_name: str
    quantity: float
    unit_price: float
    subtotal: float


class LedgerEntryResponse(BaseModel):
    id: str
    pharmacy_id: Optional[int]
    entry_type: str
    total_amount: float
    payment_method: str
    notes: Optional[str]
    confirmed_at: Optional[str]
    created_at: Optional[str]
    # Name of the person who confirmed the entry (falls back to its creator); None if unknown.
    confirmed_by_name: Optional[str] = None
    items: List[LedgerLineResponse]


class PharmacyActivityResponse(BaseModel):
    id: int
    user_name: Optional[str]
    action_type: str
    entity_type: str
    entity_id: str
    details: Dict[str, Any]
    timestamp: Optional[str]


@router.get("/daily-summary", response_model=FinancialSummaryResponse)
async def get_daily_summary(
    day: date | None = None,
    start_day: date | None = None,
    end_day: date | None = None,
    db:  AsyncSession = Depends(get_db),
    ctx: dict         = Depends(require_permission("view_reports")),
):
    if day is not None and (start_day is not None or end_day is not None):
        raise HTTPException(status_code=422, detail="Use either a single day or a date range.")
    if (start_day is None) != (end_day is None):
        raise HTTPException(status_code=422, detail="Both start_day and end_day are required for a date range.")
    if start_day is not None and end_day is not None and end_day < start_day:
        raise HTTPException(status_code=422, detail="The report end date cannot be earlier than its start date.")
    own_user_id = ctx["user_id"] if ctx["role"] == "cashier" else None
    if start_day is not None and end_day is not None:
        return await financial_summary_for_range(
            db,
            ctx["pharmacy_id"],
            start_day=start_day,
            end_day=end_day,
            user_id=own_user_id,
        )
    return await daily_financial_summary(db, ctx["pharmacy_id"], day=day, user_id=own_user_id)


@router.get("/entries", response_model=List[LedgerEntryResponse])
async def list_recent_entries(
    limit: int          = Query(20, ge=1, le=100),
    offset: int         = Query(0, ge=0, le=100000),
    entry_type: Optional[Literal["log_sale", "log_expense", "log_restock"]] = None,
    day: date | None = None,
    start_day: date | None = None,
    end_day: date | None = None,
    db:    AsyncSession = Depends(get_db),
    ctx:   dict         = Depends(require_permission("view_reports")),
):
    if day is not None and (start_day is not None or end_day is not None):
        raise HTTPException(status_code=422, detail="Use either a single day or a date range.")
    if (start_day is None) != (end_day is None):
        raise HTTPException(status_code=422, detail="Both start_day and end_day are required for a date range.")
    if start_day is not None and end_day is not None and end_day < start_day:
        raise HTTPException(status_code=422, detail="The report end date cannot be earlier than its start date.")
    pharmacy_id = ctx["pharmacy_id"]

    entry_query = (
        select(LedgerEntry)
        .options(selectinload(LedgerEntry.items))
        .where(LedgerEntry.pharmacy_id == pharmacy_id)
    )
    if day is not None:
        start_utc, end_utc, _ = local_day_bounds_utc(day)
        entry_query = entry_query.where(
            LedgerEntry.created_at >= start_utc,
            LedgerEntry.created_at < end_utc,
        )
    elif start_day is not None and end_day is not None:
        start_utc, _, _ = local_day_bounds_utc(start_day)
        _, end_utc, _ = local_day_bounds_utc(end_day)
        entry_query = entry_query.where(
            LedgerEntry.created_at >= start_utc,
            LedgerEntry.created_at < end_utc,
        )
    if entry_type is not None:
        entry_query = entry_query.where(LedgerEntry.entry_type == entry_type)
    if ctx["role"] == "cashier":
        entry_query = entry_query.where(func.coalesce(LedgerEntry.confirmed_by, LedgerEntry.created_by) == ctx["user_id"])
    # id is the tie-breaker so pages stay stable when entries share a timestamp.
    result = await db.execute(
        entry_query
        .order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
        .offset(offset)
        .limit(limit)
    )
    entries = result.scalars().all()

    # One lookup for the whole page: who confirmed (or, failing that, created) each entry.
    responsible_ids = {
        e.confirmed_by or e.created_by
        for e in entries
        if (e.confirmed_by or e.created_by) is not None
    }
    names_by_id: Dict[int, str] = {}
    if responsible_ids:
        name_rows = await db.execute(select(User.id, User.name).where(User.id.in_(responsible_ids)))
        names_by_id = {user_id: name for user_id, name in name_rows.all()}

    return [
        {
            "id": e.id,
            "pharmacy_id": e.pharmacy_id,
            "entry_type": e.entry_type,
            "total_amount": e.total_amount,
            "payment_method": e.payment_method,
            "notes": e.notes,
            "confirmed_at": e.confirmed_at.isoformat() + "Z" if e.confirmed_at else None,
            "created_at": e.created_at.isoformat() + "Z" if e.created_at else None,
            "confirmed_by_name": names_by_id.get(e.confirmed_by or e.created_by),
            "items": [
                {
                    "item_name": item.item_name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "subtotal": item.subtotal,
                }
                for item in e.items
            ]
        }
        for e in entries
    ]


@router.get("/activity", response_model=List[PharmacyActivityResponse])
async def list_pharmacy_activity(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_audit")),
):
    """Operational activity, separate from the financial ledger."""
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.pharmacy_id == ctx["pharmacy_id"])
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
    )
    output = []
    for record in result.scalars().all():
        details = {}
        if record.details_json:
            try:
                details = json.loads(record.details_json)
            except (TypeError, ValueError):
                details = {}
        output.append({
            "id": record.id,
            "user_name": record.user_name,
            "action_type": record.action_type,
            "entity_type": record.entity_type,
            "entity_id": record.entity_id,
            "details": details,
            "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        })
    return output


# ─────────────────────────────────────────────────────────────
# RECORDS TIMELINE (Session 109, W6)
#
# One newest-first list of what happened in the pharmacy: ledger entries (sales,
# expenses, restocks) plus the audit rows that are not already a ledger entry
# (product created or edited, category changes, supplier payments, staff and role
# changes, settings). Every source is gated by its own scope, and a cashier sees only
# their own rows from every source.
# ─────────────────────────────────────────────────────────────
LEDGER_KINDS = {"log_sale", "log_expense", "log_restock"}
# Product and category events: visible with view_inventory.
PRODUCT_ACTIONS = {"CREATE_PRODUCT", "UPDATE_PRODUCT", "SET_PRODUCT_CATEGORY",
                   "CREATE_CATEGORY", "RENAME_CATEGORY", "DELETE_CATEGORY"}
# Already shown as ledger entries, or personal account noise: never repeated in the timeline.
TIMELINE_HIDDEN_ACTIONS = {"CONFIRM_ACTION", "DIRECT_RESTOCK", "SELECT_PHARMACY", "RETURN_TO_ACCOUNT_SCOPE",
                           "UPDATE_PROFILE", "UPDATE_USER_PROFILE", "CREATE_USER_ACCOUNT"}
TIMELINE_MAX_OFFSET = 1000


class TimelineEventResponse(BaseModel):
    id: str
    source: Literal["ledger", "audit"]
    kind: str
    occurred_at: Optional[str]
    actor_name: Optional[str]
    # The acting member's role name (a custom role's own name) when it was recorded.
    actor_role_name: Optional[str]
    product_name: Optional[str]
    amount: Optional[float]
    entity_type: str
    entity_id: str
    details: Dict[str, Any]


@router.get("/timeline", response_model=List[TimelineEventResponse])
async def list_records_timeline(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=TIMELINE_MAX_OFFSET),
    kind: Optional[str] = Query(default=None, min_length=1, max_length=50),
    user_id: Optional[int] = Query(default=None, ge=1),
    start_day: date | None = None,
    end_day: date | None = None,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_user),
):
    _check_range(start_day, end_day)
    role, scopes = ctx["role"], ctx.get("scopes")
    can_ledger = has_permission(role, "view_reports", scopes)
    can_product = has_permission(role, "view_inventory", scopes)
    can_audit = has_permission(role, "view_audit", scopes)
    if not (can_ledger or can_product or can_audit):
        raise HTTPException(status_code=403, detail="Your role cannot view pharmacy records.")
    pharmacy_id = ctx["pharmacy_id"]
    own_only = role == "cashier"
    if own_only and user_id is not None and user_id != ctx["user_id"]:
        raise HTTPException(status_code=403, detail="You can only view your own records.")
    wanted_user = ctx["user_id"] if own_only else user_id
    window = offset + limit  # each source is read this deep, then merged and sliced
    start_utc = local_day_bounds_utc(start_day)[0] if start_day is not None else None
    end_utc = local_day_bounds_utc(end_day)[1] if end_day is not None else None
    events: List[dict] = []

    if can_ledger and (kind is None or kind in LEDGER_KINDS):
        query = select(LedgerEntry).options(selectinload(LedgerEntry.items)).where(LedgerEntry.pharmacy_id == pharmacy_id)
        if kind is not None:
            query = query.where(LedgerEntry.entry_type == kind)
        if wanted_user is not None:
            query = query.where(func.coalesce(LedgerEntry.confirmed_by, LedgerEntry.created_by) == wanted_user)
        if start_utc is not None:
            query = query.where(LedgerEntry.created_at >= start_utc, LedgerEntry.created_at < end_utc)
        entries = (await db.execute(
            query.order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc()).limit(window)
        )).scalars().all()
        responsible = {e.confirmed_by or e.created_by for e in entries if (e.confirmed_by or e.created_by) is not None}
        names: Dict[int, str] = {}
        if responsible:
            rows = await db.execute(select(User.id, User.name).where(User.id.in_(responsible)))
            names = {uid: name for uid, name in rows.all()}
        for e in entries:
            actor_id = e.confirmed_by or e.created_by
            first = e.items[0].item_name if len(e.items) == 1 else None
            events.append({
                "id": f"entry:{e.id}", "source": "ledger", "kind": e.entry_type,
                "sort": (e.created_at, f"entry:{e.id}"),
                "occurred_at": e.created_at.isoformat() + "Z" if e.created_at else None,
                "actor_name": names.get(actor_id), "actor_role_name": None,
                "product_name": first, "amount": e.total_amount,
                "entity_type": "ledger_entry", "entity_id": e.id,
                # Lines, notes and supplier come with the entry, so the web can open an event without a second request.
                "details": {
                    "payment_method": e.payment_method,
                    "item_count": len(e.items),
                    "notes": e.notes,
                    "supplier_name": getattr(e, "supplier_name", None),
                    "items": [
                        {"item_name": i.item_name, "quantity": i.quantity, "unit_price": i.unit_price, "subtotal": i.subtotal}
                        for i in e.items
                    ],
                },
            })

    if (can_product or can_audit) and (kind is None or kind not in LEDGER_KINDS):
        visible = []
        if can_product:
            visible.append(AuditLog.action_type.in_(PRODUCT_ACTIONS))
        if can_audit:
            visible.append(and_(
                AuditLog.action_type.notin_(PRODUCT_ACTIONS | TIMELINE_HIDDEN_ACTIONS),
            ))
        query = select(AuditLog).where(AuditLog.pharmacy_id == pharmacy_id, or_(*visible))
        if kind is not None:
            query = query.where(AuditLog.action_type == kind)
        if wanted_user is not None:
            query = query.where(AuditLog.user_id == wanted_user)
        if start_utc is not None:
            query = query.where(AuditLog.timestamp >= start_utc, AuditLog.timestamp < end_utc)
        for record in (await db.execute(
            query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(window)
        )).scalars().all():
            try:
                details = json.loads(record.details_json) if record.details_json else {}
            except (TypeError, ValueError):
                details = {}
            if not isinstance(details, dict):
                details = {}
            role_name = details.pop("role_name", None)
            events.append({
                "id": f"audit:{record.id}", "source": "audit", "kind": record.action_type,
                "sort": (record.timestamp, f"audit:{record.id}"),
                "occurred_at": record.timestamp.isoformat() + "Z" if record.timestamp else None,
                "actor_name": record.user_name, "actor_role_name": role_name,
                "product_name": details.get("name_ar") or details.get("name"),
                "amount": None, "entity_type": record.entity_type, "entity_id": record.entity_id,
                "details": details,
            })

    events.sort(key=lambda event: (event["sort"][0] or datetime.min, event["sort"][1]), reverse=True)
    return [{key: value for key, value in event.items() if key != "sort"} for event in events[offset:offset + limit]]


# ─────────────────────────────────────────────────────────────
# SUPPLIER PAYABLES
#
# A payable is a credit restock. What is still owed is the entry total minus its
# settlements. Settlements are not expenses and never change profit (cost of goods
# is recognised at sale from FIFO unit_cost).
# ─────────────────────────────────────────────────────────────
PAYABLE_EPS = 0.005  # half a piastre: amounts are rounded to 2 places when written
# The same number as a Float literal for SQL: a bare 0.005 compared with a Money column would be
# bound as a Money value and rounded up to 0.01.
_SQL_EPS = literal(PAYABLE_EPS, Float)
PayableStatus = Literal["unpaid", "partly_paid", "paid"]


class SettlementResponse(BaseModel):
    id: int
    amount: float
    payment_method: str
    paid_at: Optional[str]
    paid_by_name: Optional[str]


class PayableResponse(BaseModel):
    id: str
    supplier_name: Optional[str]
    total_amount: float
    paid_amount: float
    remaining_amount: float
    status: PayableStatus
    notes: Optional[str]
    confirmed_at: Optional[str]
    created_at: Optional[str]
    confirmed_by_name: Optional[str] = None
    items: List[LedgerLineResponse]
    settlements: List[SettlementResponse]


class PayablesSummaryResponse(BaseModel):
    total_remaining: float
    open_count: int
    unpaid_count: int
    partly_paid_count: int
    paid_count: int
    tracking_started_at: Optional[str]


class SettlementCreate(BaseModel):
    # The payer is always the signed-in user, so no payer field is accepted.
    model_config = ConfigDict(extra="forbid")
    amount: MoneyIn = Field(gt=0, le=100_000_000, allow_inf_nan=False)
    payment_method: Literal["cash", "card"]


def _payable_status(total: float, paid: float) -> str:
    if paid >= total - PAYABLE_EPS:
        return "paid"
    if paid <= PAYABLE_EPS:
        return "unpaid"
    return "partly_paid"


def _check_range(start_day: date | None, end_day: date | None) -> None:
    if (start_day is None) != (end_day is None):
        raise HTTPException(status_code=422, detail="Both start_day and end_day are required for a date range.")
    if start_day is not None and end_day is not None and end_day < start_day:
        raise HTTPException(status_code=422, detail="The report end date cannot be earlier than its start date.")


async def _payables_tracking_start(db: AsyncSession) -> Optional[datetime]:
    """Naive UTC time when payables tracking began (the applied_at of migration v12)."""
    row = (await db.execute(text("SELECT applied_at FROM schema_migrations WHERE version = 12"))).first()
    if not row or row[0] is None:
        return None
    value = row[0]
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _payables_conditions(ctx: dict, tracking_start: Optional[datetime], start_day: date | None, end_day: date | None) -> list:
    conditions = [
        LedgerEntry.pharmacy_id == ctx["pharmacy_id"],
        LedgerEntry.entry_type == "log_restock",
        LedgerEntry.payment_method == "credit",
    ]
    if tracking_start is not None:
        conditions.append(LedgerEntry.created_at >= tracking_start)
    if start_day is not None and end_day is not None:
        start_utc, _, _ = local_day_bounds_utc(start_day)
        _, end_utc, _ = local_day_bounds_utc(end_day)
        conditions += [LedgerEntry.created_at >= start_utc, LedgerEntry.created_at < end_utc]
    if ctx["role"] == "cashier":
        conditions.append(func.coalesce(LedgerEntry.confirmed_by, LedgerEntry.created_by) == ctx["user_id"])
    return conditions


def _paid_subquery(pharmacy_id: int):
    return (
        select(
            RestockSettlement.entry_id.label("entry_id"),
            func.coalesce(func.sum(RestockSettlement.amount), 0.0).label("paid"),
        )
        .where(RestockSettlement.pharmacy_id == pharmacy_id)
        .group_by(RestockSettlement.entry_id)
        .subquery()
    )


async def _user_names(db: AsyncSession, user_ids: set) -> Dict[int, str]:
    user_ids = {user_id for user_id in user_ids if user_id is not None}
    if not user_ids:
        return {}
    rows = await db.execute(select(User.id, User.name).where(User.id.in_(user_ids)))
    return {user_id: name for user_id, name in rows.all()}


async def _build_payables(db: AsyncSession, pharmacy_id: int, rows: list) -> List[dict]:
    """rows: (LedgerEntry with items loaded, paid amount) pairs."""
    if not rows:
        return []
    settlement_rows = (await db.execute(
        select(RestockSettlement)
        .where(
            RestockSettlement.pharmacy_id == pharmacy_id,
            RestockSettlement.entry_id.in_([entry.id for entry, _ in rows]),
        )
        .order_by(RestockSettlement.paid_at.asc(), RestockSettlement.id.asc())
    )).scalars().all()
    names = await _user_names(
        db,
        {s.paid_by for s in settlement_rows} | {entry.confirmed_by or entry.created_by for entry, _ in rows},
    )
    settlements_by_entry: Dict[str, List[dict]] = {}
    for settlement in settlement_rows:
        settlements_by_entry.setdefault(settlement.entry_id, []).append({
            "id": settlement.id,
            "amount": settlement.amount,
            "payment_method": settlement.payment_method,
            "paid_at": settlement.paid_at.isoformat() + "Z" if settlement.paid_at else None,
            "paid_by_name": names.get(settlement.paid_by),
        })
    output = []
    for entry, paid_raw in rows:
        total = round_money(entry.total_amount)
        paid = round_money(paid_raw)
        status = _payable_status(total, paid)
        output.append({
            "id": entry.id,
            "supplier_name": entry.supplier_name,
            "total_amount": total,
            "paid_amount": paid,
            "remaining_amount": 0.0 if status == "paid" else round_money(total - paid),
            "status": status,
            "notes": entry.notes,
            "confirmed_at": entry.confirmed_at.isoformat() + "Z" if entry.confirmed_at else None,
            "created_at": entry.created_at.isoformat() + "Z" if entry.created_at else None,
            "confirmed_by_name": names.get(entry.confirmed_by or entry.created_by),
            "items": [
                {
                    "item_name": item.item_name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "subtotal": item.subtotal,
                }
                for item in entry.items
            ],
            "settlements": settlements_by_entry.get(entry.id, []),
        })
    return output


@router.get("/payables/summary", response_model=PayablesSummaryResponse)
async def payables_summary(
    start_day: date | None = None,
    end_day: date | None = None,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_reports")),
):
    _check_range(start_day, end_day)
    tracking_start = await _payables_tracking_start(db)
    paid_sq = _paid_subquery(ctx["pharmacy_id"])
    rows = (await db.execute(
        select(LedgerEntry.total_amount, func.coalesce(paid_sq.c.paid, 0.0))
        .outerjoin(paid_sq, paid_sq.c.entry_id == LedgerEntry.id)
        .where(*_payables_conditions(ctx, tracking_start, start_day, end_day))
    )).all()
    counts = {"unpaid": 0, "partly_paid": 0, "paid": 0}
    open_balances = []
    for total_raw, paid_raw in rows:
        total, paid = round_money(total_raw), round_money(paid_raw)
        status = _payable_status(total, paid)
        counts[status] += 1
        if status != "paid":
            open_balances.append(round_money(total - paid))
    total_remaining = money_sum(open_balances)
    return {
        "total_remaining": total_remaining,
        "open_count": counts["unpaid"] + counts["partly_paid"],
        "unpaid_count": counts["unpaid"],
        "partly_paid_count": counts["partly_paid"],
        "paid_count": counts["paid"],
        "tracking_started_at": tracking_start.isoformat() + "Z" if tracking_start else None,
    }


@router.get("/payables", response_model=List[PayableResponse])
async def list_payables(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
    status: Optional[PayableStatus] = None,
    start_day: date | None = None,
    end_day: date | None = None,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_reports")),
):
    """Credit restocks with what was paid and what remains, newest first."""
    _check_range(start_day, end_day)
    tracking_start = await _payables_tracking_start(db)
    paid_sq = _paid_subquery(ctx["pharmacy_id"])
    paid_col = func.coalesce(paid_sq.c.paid, 0.0)
    query = (
        select(LedgerEntry, paid_col.label("paid"))
        .options(selectinload(LedgerEntry.items))
        .outerjoin(paid_sq, paid_sq.c.entry_id == LedgerEntry.id)
        .where(*_payables_conditions(ctx, tracking_start, start_day, end_day))
    )
    if status == "paid":
        query = query.where(paid_col >= LedgerEntry.total_amount - _SQL_EPS)
    elif status == "unpaid":
        query = query.where(paid_col < LedgerEntry.total_amount - _SQL_EPS, paid_col <= _SQL_EPS)
    elif status == "partly_paid":
        query = query.where(paid_col < LedgerEntry.total_amount - _SQL_EPS, paid_col > _SQL_EPS)
    result = await db.execute(
        query.order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc()).offset(offset).limit(limit)
    )
    return await _build_payables(db, ctx["pharmacy_id"], [(row[0], row[1]) for row in result.all()])


@router.post("/entries/{entry_id}/settlements", response_model=PayableResponse)
async def record_settlement(
    entry_id: str,
    req: SettlementCreate,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("manage_payables")),
):
    """Records a payment to a supplier against one credit restock."""
    pharmacy_id = ctx["pharmacy_id"]
    result = await db.execute(
        select(LedgerEntry)
        .options(selectinload(LedgerEntry.items))
        .where(
            LedgerEntry.id == entry_id,
            LedgerEntry.pharmacy_id == pharmacy_id,
            LedgerEntry.entry_type == "log_restock",
            LedgerEntry.payment_method == "credit",
        )
        .with_for_update()
    )
    entry = result.scalars().first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Credit restock not found in this pharmacy.")

    amount = round_money(req.amount)
    if amount <= 0:
        raise HTTPException(status_code=422, detail="The payment amount must be at least 0.01.")
    paid_before = round_money((await db.execute(
        select(func.coalesce(func.sum(RestockSettlement.amount), 0.0)).where(
            RestockSettlement.pharmacy_id == pharmacy_id,
            RestockSettlement.entry_id == entry.id,
        )
    )).scalar_one())
    total = round_money(entry.total_amount)
    remaining = round_money(total - paid_before)
    if remaining <= PAYABLE_EPS:
        raise HTTPException(status_code=409, detail="This restock is already fully paid.")
    if amount > remaining + PAYABLE_EPS:
        raise HTTPException(status_code=409, detail="The payment exceeds the remaining balance of this restock.")

    db.add(RestockSettlement(
        pharmacy_id=pharmacy_id,
        entry_id=entry.id,
        amount=amount,
        payment_method=req.payment_method,
        paid_by=ctx["user_id"],
        paid_at=utc_now_naive(),
    ))
    db.add(AuditLog(
        pharmacy_id=pharmacy_id,
        action_type="PAY_SUPPLIER",
        entity_type="ledger_entry",
        entity_id=entry.id,
        user_id=ctx["user_id"],
        user_name=ctx.get("user_name"),
        user_role=ctx["role"],
        details_json=json.dumps({
            "role_name": ctx.get("role_name"),
            "amount": amount,
            "payment_method": req.payment_method,
            "remaining_after": round_money(remaining - amount),
            "supplier_name": entry.supplier_name,
        }, ensure_ascii=False),
        timestamp=utc_now_naive(),
    ))
    await db.flush()
    payable = (await _build_payables(db, pharmacy_id, [(entry, round_money(paid_before + amount))]))[0]
    await db.commit()
    return payable
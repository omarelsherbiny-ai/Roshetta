# server/app/api/ai.py
"""AI-safe read surface for MicroMind's OpenAPI Toolkit (mounted at /ai).

Why a separate app: the main /openapi.json lists every route (auth, staff,
pharmacies, settlements...). The toolkit turns every listed operation into a tool,
so it must import /ai/openapi.json instead, which lists only the routes below.

Rules baked in:
- Read-only. No route here writes data; sale, restock and expense stay proposals.
- Identity and pharmacy come only from the Bearer token (same dependencies as the
  main API). No route accepts pharmacy_id, user_id or any identity argument.
- Responses use their own models that leave out buy prices, costs, notes, ids of
  people and every personal field, so safety does not depend on a filter list.
- Result sizes are capped.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from server.app.api.inventory import (
    _like_pattern,
    get_inventory_price_history,
    inventory_summary,
    list_category_details,
)
from server.app.api.ledger import (
    get_daily_summary,
    list_payables,
    list_records_timeline,
    list_recent_entries,
    payables_summary,
)
from server.app.api.me import get_my_activity
from server.app.api.ai_propose import propose_router
from server.app.api.staff import list_roles
from server.app.db.models import InventoryBatch, InventoryItem, has_permission
from server.app.db.session import get_db
from server.app.services.fuzzy_match import rank_matches
from server.app.services.rate_limit import ai_limiter
from server.app.services.rbac import (
    get_current_identity,
    get_current_identity_allow_ai,
    get_current_user,
    require_permission,
)

def ai_rate_limit_key(ctx: dict) -> tuple:
    """Budget key: the pharmacy and the member from the token's own context."""
    member = next((ctx[name] for name in ("user_id", "id", "sub") if ctx.get(name) is not None), None)
    return (ctx.get("pharmacy_id"), member)


async def ai_rate_limit(ctx: dict = Depends(get_current_user)) -> None:
    """Runs on every /ai route after the token is accepted (so unsigned calls never
    use up a budget). Over the limit: 429 with Retry-After, which the toolkit JS
    already explains to the model."""
    wait = ai_limiter.check(ai_rate_limit_key(ctx))
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Wait a moment and try again.",
            headers={"Retry-After": str(wait)},
        )


router = APIRouter(dependencies=[Depends(ai_rate_limit)])

# Days are Cairo days (the same zone the ledger and the staff schedules use).
CAIRO = ZoneInfo("Africa/Cairo")
# How far ahead "expiring soon" looks when the caller does not say. A product's catalog
# expiry is the earliest expiry among its lots with stock (ISO YYYY-MM-DD text), so a text
# comparison with an ISO cutoff is a date comparison.
EXPIRY_WINDOW_DEFAULT_DAYS = 30


def _expiry_cutoff(days: int) -> str:
    return (datetime.now(CAIRO).date() + timedelta(days=days)).isoformat()


class AIItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    barcode: Optional[str]
    name_ar: str
    name_en: str
    active_ingredient: Optional[str]
    category: Optional[str]
    stock_qty: float
    min_threshold: float
    unit_sell_price: float
    expiry_date: Optional[str]


class AIMatchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query_name: str = Field(min_length=1, max_length=100)


class AIMatchResponse(BaseModel):
    found: bool
    matched_item: Optional[AIItem] = None
    alternatives: List[AIItem] = Field(default_factory=list)
    suggestions: List[AIItem] = Field(default_factory=list)


class AIBatch(BaseModel):
    id: int
    batch_number: Optional[str]
    quantity: float
    unit_sell_price: float
    expiry_date: Optional[str]
    received_at: Optional[str]


class AIActivity(BaseModel):
    period: Literal["day", "week", "month", "all"]
    sales_count: int
    expenses_count: int
    restocks_count: int
    total_sales: float
    total_expenses: float
    total_restock: float
    items_sold: float
    items_restocked: float
    net: float


class AILine(BaseModel):
    item_name: str
    quantity: float
    unit_price: float
    subtotal: float


class AIEntry(BaseModel):
    id: str
    entry_type: str
    total_amount: float
    payment_method: str
    created_at: Optional[str]
    items: List[AILine]


class AISettlement(BaseModel):
    amount: float
    payment_method: str
    paid_at: Optional[str]


class AIPayable(BaseModel):
    id: str
    supplier_name: Optional[str]
    total_amount: float
    paid_amount: float
    remaining_amount: float
    status: Literal["unpaid", "partly_paid", "paid"]
    created_at: Optional[str]
    items: List[AILine]
    settlements: List[AISettlement]


class AIPayablesSummary(BaseModel):
    total_remaining: float
    open_count: int
    unpaid_count: int
    partly_paid_count: int
    paid_count: int
    tracking_started_at: Optional[str]


class AISummary(BaseModel):
    """Sales and expenses for one day or a range. No cost of goods and no profit."""
    date: str
    total_sales: float
    total_expenses: float
    sales_count: int
    expenses_count: int


class AIInventorySummary(BaseModel):
    """Stock counts and the selling value. The stock cost value is left out."""
    item_count: int
    total_units: float
    potential_sales_value: float


class AICategory(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    item_count: int


class AIPriceChange(BaseModel):
    """One selling-price change. Buy prices and the person who changed it are left out."""
    previous_unit_sell_price: Optional[float]
    unit_sell_price: float
    recorded_at: Optional[str]


class AIRole(BaseModel):
    name: str
    scopes: List[str]
    assigned_count: int


class AIRolesList(BaseModel):
    roles: List[AIRole]


class AITimelineEvent(BaseModel):
    """One record. No person names, ids or details: only what happened, when, the
    role name of who did it, the product and the amount."""
    source: Literal["ledger", "audit"]
    kind: str
    occurred_at: Optional[str]
    actor_role_name: Optional[str]
    product_name: Optional[str]
    amount: Optional[float]


@router.get(
    "/items",
    operation_id="search_inventory",
    summary="List or search this pharmacy's products. Leave search and category empty to list ALL products (alphabetical, up to limit 50, page with offset); or search by name, active ingredient or barcode, or filter by category",
    response_model=List[AIItem],
)
async def search_inventory(
    search: Optional[str] = Query(default=None, max_length=100, description="Optional. Leave empty to list all products."),
    category: Optional[str] = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=1000, description="How many products to skip, to read the next page."),
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_inventory")),
):
    query = select(InventoryItem).where(InventoryItem.pharmacy_id == ctx["pharmacy_id"])
    if search and search.strip():
        pattern = _like_pattern(search.strip())
        query = query.where(or_(
            InventoryItem.name_ar.ilike(pattern, escape="\\"),
            InventoryItem.name_en.ilike(pattern, escape="\\"),
            InventoryItem.active_ingredient.ilike(pattern, escape="\\"),
            InventoryItem.barcode.ilike(pattern, escape="\\"),
        ))
    if category and category.strip():
        query = query.where(InventoryItem.category == category.strip())
    result = await db.execute(
        query.order_by(InventoryItem.name_ar, InventoryItem.id).offset(offset).limit(limit)
    )
    return result.scalars().all()


@router.post(
    "/match",
    operation_id="match_product",
    summary="Find one product by a typed or spoken name; when none matches exactly it returns the closest products (typos, missing or swapped letters) as suggestions for the user to choose from",
    response_model=AIMatchResponse,
)
async def match_product(
    req: AIMatchRequest,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_inventory")),
):
    pharmacy_id = ctx["pharmacy_id"]
    query_str = req.query_name
    pattern = _like_pattern(query_str)
    exact = await db.execute(
        select(InventoryItem).where(
            InventoryItem.pharmacy_id == pharmacy_id,
            or_(
                InventoryItem.name_ar.ilike(pattern, escape="\\"),
                InventoryItem.name_en.ilike(pattern, escape="\\"),
            ),
        ).order_by(InventoryItem.name_ar, InventoryItem.id).limit(4)
    )
    matches = exact.scalars().all()
    if matches:
        return {"found": True, "matched_item": matches[0], "alternatives": matches[1:4]}

    # No name contains the text: rank every product of this pharmacy by closeness, so a
    # typo anywhere in the name still finds the product. Only this pharmacy's rows are read.
    everything = await db.execute(
        select(InventoryItem).where(InventoryItem.pharmacy_id == pharmacy_id)
    )
    items = {item.id: item for item in everything.scalars().all()}
    ranked = rank_matches(
        query_str,
        ((item.id, (item.name_ar, item.name_en)) for item in items.values()),
        limit=5,
    )
    return {"found": False, "suggestions": [items[ident] for ident in ranked]}


@router.get(
    "/items/{item_id}/batches",
    operation_id="get_item_batches",
    summary="List the stock lots of one product, oldest first (quantity, sell price, expiry)",
    response_model=List[AIBatch],
)
async def get_item_batches(
    item_id: int = Path(ge=1),
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_inventory")),
):
    owned = await db.execute(select(InventoryItem.id).where(
        InventoryItem.id == item_id,
        InventoryItem.pharmacy_id == ctx["pharmacy_id"],
    ))
    if owned.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Product not found in this pharmacy.")
    result = await db.execute(
        select(InventoryBatch)
        .where(
            InventoryBatch.item_id == item_id,
            InventoryBatch.pharmacy_id == ctx["pharmacy_id"],
        )
        .order_by(InventoryBatch.created_at.asc(), InventoryBatch.id.asc())
    )
    return [{
        "id": row.id,
        "batch_number": row.batch_number,
        "quantity": row.quantity,
        "unit_sell_price": row.unit_sell_price,
        "expiry_date": row.expiry_date,
        "received_at": row.created_at.isoformat() + "Z" if row.created_at else None,
    } for row in result.scalars().all()]


@router.get(
    "/activity",
    operation_id="get_my_activity",
    summary="Totals of the signed-in user's own sales, expenses and restocks for a period",
    response_model=AIActivity,
)
async def get_my_activity_summary(
    period: str = Query(default="day", pattern="^(day|week|month|all)$"),
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_user),
):
    # Reuse the real endpoint's logic. pharmacy_id=None means "the token's pharmacy",
    # so the model cannot point it at another one. recent_entries (notes, payment) is dropped.
    full = await get_my_activity(pharmacy_id=None, period=period, db=db, ctx=ctx)
    return {key: full[key] for key in AIActivity.model_fields}


# The three ledger tools below call the real endpoint functions in-process with the
# token's own context, so scopes, cashier scoping and tenant filters are the main API's.
# Their response models here drop notes, confirmed_by_name, paid_by_name and pharmacy_id.

@router.get(
    "/entries",
    operation_id="list_ledger_entries",
    summary="List recent sales, expenses and restocks (use day, or start_day with end_day)",
    response_model=List[AIEntry],
)
async def list_ledger_entries(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=1000),
    entry_type: Optional[Literal["log_sale", "log_expense", "log_restock"]] = None,
    day: Optional[date] = None,
    start_day: Optional[date] = None,
    end_day: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_reports")),
):
    return await list_recent_entries(
        limit=limit, offset=offset, entry_type=entry_type, day=day,
        start_day=start_day, end_day=end_day, db=db, ctx=ctx,
    )


@router.get(
    "/payables",
    operation_id="list_supplier_payables",
    summary="List credit restocks with what was paid and what is still owed, newest first",
    response_model=List[AIPayable],
)
async def list_supplier_payables(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=1000),
    status: Optional[Literal["unpaid", "partly_paid", "paid"]] = None,
    start_day: Optional[date] = None,
    end_day: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_reports")),
):
    return await list_payables(
        limit=limit, offset=offset, status=status,
        start_day=start_day, end_day=end_day, db=db, ctx=ctx,
    )


@router.get(
    "/payables/summary",
    operation_id="get_payables_summary",
    summary="Total still owed to suppliers and how many restocks are unpaid, partly paid or paid",
    response_model=AIPayablesSummary,
)
async def get_payables_summary(
    start_day: Optional[date] = None,
    end_day: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_reports")),
):
    return await payables_summary(start_day=start_day, end_day=end_day, db=db, ctx=ctx)


# ---- Session 109 (W8 a): more read tools. Each wraps the real endpoint function with the
# token's own context, so its scope check, cashier scoping and tenant filter run
# unchanged; the response model here is what removes costs, profit, ids and names.

@router.get(
    "/summary",
    operation_id="get_sales_summary",
    summary="Sales and expenses totals for one day (day) or a range (start_day with end_day)",
    response_model=AISummary,
)
async def get_sales_summary(
    day: Optional[date] = None,
    start_day: Optional[date] = None,
    end_day: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_reports")),
):
    return await get_daily_summary(day=day, start_day=start_day, end_day=end_day, db=db, ctx=ctx)


@router.get(
    "/inventory/summary",
    operation_id="get_inventory_summary",
    summary="How many products and units are in stock and their total selling value",
    response_model=AIInventorySummary,
)
async def get_inventory_summary(
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_inventory")),
):
    return await inventory_summary(db=db, ctx=ctx)


@router.get(
    "/categories",
    operation_id="list_categories",
    summary="Product categories of this pharmacy with how many products each holds",
    response_model=List[AICategory],
)
async def list_categories(
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_inventory")),
):
    return await list_category_details(db=db, ctx=ctx)


class AIPharmacySummary(BaseModel):
    """A one-call overview. Each part appears only when this member's role may see it;
    `omitted` names the parts left out. No cost of goods, no profit, no names."""
    day: str
    expiry_window_days: int
    omitted: List[Literal["stock", "sales", "payables"]]
    sales_scope: Optional[Literal["pharmacy", "own"]] = None
    stock: Optional[AIInventorySummary] = None
    low_stock_count: Optional[int] = None
    out_of_stock_count: Optional[int] = None
    expiring_count: Optional[int] = None
    sales_today: Optional[AISummary] = None
    payables: Optional[AIPayablesSummary] = None


@router.get(
    "/pharmacy-summary",
    operation_id="get_pharmacy_summary",
    summary="One-call overview of the pharmacy for today (Cairo day): stock totals, low, out-of-stock and expiring product counts, today's sales and expenses, and what is owed to suppliers; parts this role may not see are listed in omitted",
    response_model=AIPharmacySummary,
)
async def get_pharmacy_summary(
    expiring_within_days: int = Query(default=EXPIRY_WINDOW_DEFAULT_DAYS, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_user),
):
    role, scopes = ctx["role"], ctx.get("scopes")
    can_stock = has_permission(role, "view_inventory", scopes)
    can_reports = has_permission(role, "view_reports", scopes)
    if not (can_stock or can_reports):
        raise HTTPException(status_code=403, detail="This role cannot view the pharmacy summary.")
    pharmacy_id = ctx["pharmacy_id"]
    is_cashier = role == "cashier"
    out: dict = {
        "day": datetime.now(CAIRO).date().isoformat(),
        "expiry_window_days": expiring_within_days,
        "omitted": [],
    }

    if can_stock:
        out["stock"] = await inventory_summary(db=db, ctx=ctx)
        counts = {}
        for name, conditions in (
            ("low_stock_count", [InventoryItem.stock_qty <= InventoryItem.min_threshold]),
            ("out_of_stock_count", [InventoryItem.stock_qty <= 0]),
            ("expiring_count", [
                InventoryItem.stock_qty > 0,
                InventoryItem.expiry_date.is_not(None),
                InventoryItem.expiry_date != "",
                InventoryItem.expiry_date <= _expiry_cutoff(expiring_within_days),
            ]),
        ):
            result = await db.execute(
                select(func.count(InventoryItem.id)).where(InventoryItem.pharmacy_id == pharmacy_id, *conditions)
            )
            counts[name] = int(result.scalar_one() or 0)
        out.update(counts)
    else:
        out["omitted"].append("stock")

    if can_reports:
        # day=None is today's Cairo day (the same call chat.py makes); a cashier's totals
        # are their own entries only, so the scope is reported.
        out["sales_today"] = await get_daily_summary(day=None, start_day=None, end_day=None, db=db, ctx=ctx)
        out["sales_scope"] = "own" if is_cashier else "pharmacy"
        if is_cashier:
            # What the pharmacy owes suppliers is not a cashier's business.
            out["omitted"].append("payables")
        else:
            out["payables"] = await payables_summary(start_day=None, end_day=None, db=db, ctx=ctx)
    else:
        out["omitted"].extend(["sales", "payables"])
    return out


@router.get(
    "/items/{item_id}/price-history",
    operation_id="get_item_price_history",
    summary="Selling-price changes of one product, newest first",
    response_model=List[AIPriceChange],
)
async def get_item_price_history(
    item_id: int = Path(ge=1),
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_inventory")),
):
    return await get_inventory_price_history(item_id=item_id, limit=50, db=db, ctx=ctx)


@router.get(
    "/timeline",
    operation_id="list_records_timeline",
    summary="Newest-first records: sales, expenses, restocks, product and category changes, staff and settings changes (only what this role may see)",
    response_model=List[AITimelineEvent],
)
async def list_timeline(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=1000),
    kind: Optional[str] = Query(default=None, min_length=1, max_length=50),
    start_day: Optional[date] = None,
    end_day: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_user),
):
    # The endpoint decides what each source shows: ledger needs view_reports, product
    # events view_inventory, everything else view_audit; a cashier sees only own rows.
    return await list_records_timeline(
        limit=limit, offset=offset, kind=kind, user_id=None,
        start_day=start_day, end_day=end_day, db=db, ctx=ctx,
    )


@router.get(
    "/roles",
    operation_id="list_roles",
    summary="Custom roles of this pharmacy with their scopes and how many members hold each (owner only)",
    response_model=AIRolesList,
)
async def list_pharmacy_roles(
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_user),
):
    # list_roles itself answers 403 unless the caller is the owner.
    full = await list_roles(pharmacy_id=ctx["pharmacy_id"], db=db, ctx=ctx)
    return {"roles": full["roles"]}


def _strip_identity_headers(schema: dict) -> dict:
    """Remove the `authorization` header parameter FastAPI lists on every operation.
    The toolkit would offer it to the model as an argument; the tool code adds the
    Bearer token itself and drops any header the model supplies."""
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            kept = [
                parameter for parameter in operation.get("parameters", [])
                if not (parameter.get("in") == "header"
                        and str(parameter.get("name", "")).lower() == "authorization")
            ]
            if kept:
                operation["parameters"] = kept
            else:
                operation.pop("parameters", None)
    return schema


def create_ai_app(public_url: str = "") -> FastAPI:
    """Build the sub-app mounted at /ai. public_url is the externally reachable base
    (for example the HTTPS tunnel). The spec must carry an absolute `servers` entry:
    FastAPI writes none by default, and a toolkit that reads servers[0] fails without it."""
    base = (public_url or "").strip().rstrip("/")
    if base and not base.startswith(("https://", "http://")):
        raise ValueError("AI_PUBLIC_URL must start with https:// (or http:// for local tests).")
    servers = [{"url": f"{base}/ai" if base else "/ai"}]
    return _build(servers)


def _build(servers: list) -> FastAPI:
    ai_app = FastAPI(
        title="Roshetta AI read tools",
        version="1.0.0",
        description="Read-only, tenant-scoped tools for the MicroMind assistant. No writes.",
        servers=servers,
        root_path_in_servers=False,  # the mount would otherwise insert a relative "/ai" first
        docs_url=None,
        redoc_url=None,
    )
    ai_app.include_router(router)
    ai_app.include_router(propose_router, dependencies=[Depends(ai_rate_limit)])
    # Only this sub-app accepts the short-lived AI token (aud = "ai"). The main API
    # refuses it in get_current_identity, so a leaked AI token cannot reach /api.
    ai_app.dependency_overrides[get_current_identity] = get_current_identity_allow_ai

    default_openapi = ai_app.openapi

    def openapi_without_identity_headers() -> dict:
        if ai_app.openapi_schema is None:
            _strip_identity_headers(default_openapi())
        return ai_app.openapi_schema

    ai_app.openapi = openapi_without_identity_headers
    return ai_app
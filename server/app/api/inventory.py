# server/app/api/inventory.py
import json
import uuid
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_, and_, case, func, update

from server.app.db.money import MoneyIn, round_money
from server.app.db.session import get_db
from server.app.db.models import Category, InventoryItem, InventoryBatch, InventoryPriceHistory, AuditLog, User
from server.app.services.rbac import require_permission
from server.app.services.clock import utc_now_naive
from server.app.services.expiry import apply_typed_expiry, sync_item_expiry

router = APIRouter(prefix="/api/inventory", tags=["Inventory"])


class InventoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    barcode: Optional[str]
    name_ar: str
    name_en: str
    active_ingredient: Optional[str]
    category: Optional[str]
    stock_qty: float
    min_threshold: float
    unit_buy_price: float
    unit_sell_price: float
    expiry_date: Optional[str]
    created_at: Optional[datetime]


class InventorySummaryResponse(BaseModel):
    item_count: int
    total_units: float
    potential_sales_value: float
    stock_cost_value: Optional[float]
    stock_cost_value_complete: bool


class InventoryPriceHistoryResponse(BaseModel):
    id: int
    previous_unit_buy_price: Optional[float]
    previous_unit_sell_price: Optional[float]
    unit_buy_price: float
    unit_sell_price: float
    changed_by: int
    recorded_at: Optional[str]


class InventoryBatchResponse(BaseModel):
    id: int
    batch_number: Optional[str]
    quantity: float
    unit_buy_price: float
    unit_sell_price: float
    expiry_date: Optional[str]
    total_cost: float
    total_retail: float
    created_at: Optional[str]


class ProductMutationResponse(BaseModel):
    success: bool
    message: str
    item: InventoryItemResponse


class InventoryMatchResponse(BaseModel):
    found: bool
    matched_item: Optional[InventoryItemResponse] = None
    alternatives: List[InventoryItemResponse] = Field(default_factory=list)
    query_name: Optional[str] = None
    suggestions: List[InventoryItemResponse] = Field(default_factory=list)
    message: Optional[str] = None


class RestockResponse(ProductMutationResponse):
    old_stock: float
    new_stock: float
    total_cost: float


def _like_pattern(term: str) -> str:
    """Contains-pattern for ilike(..., escape="\\"): a typed % or _ is matched literally."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _validate_expiry_date(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Expiry date must use YYYY-MM-DD format.") from exc
    if parsed.strftime("%Y-%m-%d") != value:
        raise ValueError("Expiry date must use YYYY-MM-DD format.")
    return value


class ProductDetailsPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name_ar:           str = Field(min_length=1, max_length=150)
    name_en:           str = Field(min_length=1, max_length=150)
    barcode:           Optional[str] = Field(default=None, max_length=50)
    active_ingredient: Optional[str] = Field(default=None, max_length=150)
    category:          Optional[str] = Field(default=None, max_length=50)
    min_threshold:     float = Field(default=5.0, ge=1, le=1_000_000, allow_inf_nan=False)
    unit_buy_price:    MoneyIn = Field(default=0.0, ge=0, le=100_000_000, allow_inf_nan=False)
    unit_sell_price:   MoneyIn = Field(gt=0, le=100_000_000, allow_inf_nan=False)
    expiry_date:       Optional[str] = Field(default=None, max_length=20)

    @field_validator("expiry_date")
    @classmethod
    def validate_expiry_date(cls, value: Optional[str]) -> Optional[str]:
        return _validate_expiry_date(value)


class ProductPayload(ProductDetailsPayload):
    model_config = ConfigDict(str_strip_whitespace=True)
    stock_qty: float = Field(default=0.0, ge=0, le=1_000_000, allow_inf_nan=False)
    batch_number: Optional[str] = Field(default=None, max_length=60)


class ProductUpdatePayload(ProductDetailsPayload):
    # Accept the legacy field only to return a clear conflict to older clients.
    stock_qty: Optional[float] = Field(default=None, ge=0, le=1_000_000, allow_inf_nan=False)


class MatchProductRequest(BaseModel):
    query_name: str


CATEGORY_NAME_MAX = 40  # same limit the categories screen has always used


class CategoryNamePayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=CATEGORY_NAME_MAX)


class CategoryDetailResponse(BaseModel):
    id: int
    name: str
    item_count: int


class CategoryMutationResponse(BaseModel):
    success: bool
    message: str
    category: Optional[CategoryDetailResponse] = None
    affected_items: int = 0


def _clean_category_name(raw: Optional[str]) -> Optional[str]:
    """Collapses inner whitespace; blank becomes None (a product may have no category)."""
    if raw is None:
        return None
    name = " ".join(raw.split())
    return name or None


async def _find_category(db: AsyncSession, pharmacy_id: int, name: str, exclude_id: Optional[int] = None):
    query = select(Category).where(
        Category.pharmacy_id == pharmacy_id,
        func.lower(Category.name) == name.lower(),
    )
    if exclude_id is not None:
        query = query.where(Category.id != exclude_id)
    return (await db.execute(query.limit(1))).scalars().first()


async def _ensure_category(db: AsyncSession, pharmacy_id: int, raw: Optional[str]) -> Optional[str]:
    """Returns the stored spelling of a category, creating its row when missing.

    None or blank means "no category". An existing name in another letter case is
    reused so the list never splits into near-duplicates.
    """
    name = _clean_category_name(raw)
    if name is None:
        return None
    if len(name) > 50:
        raise HTTPException(status_code=422, detail="Category name is too long.")
    existing = await _find_category(db, pharmacy_id, name)
    if existing:
        return existing.name
    db.add(Category(pharmacy_id=pharmacy_id, name=name, created_at=utc_now_naive()))
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The category was created at the same moment by someone else. Try again.",
        ) from exc
    return name


async def _audit_category(db: AsyncSession, ctx: dict, action_type: str, entity_id: str, details: dict) -> None:
    user_res = await db.execute(select(User).where(User.id == ctx["user_id"]))
    user_obj = user_res.scalars().first()
    db.add(AuditLog(
        pharmacy_id=ctx["pharmacy_id"],
        action_type=action_type,
        entity_type="category",
        entity_id=entity_id,
        user_id=ctx["user_id"],
        user_name=user_obj.name if user_obj else f"User #{ctx['user_id']}",
        user_role=ctx["role"],
        details_json=json.dumps({**details, "role_name": ctx.get("role_name")}, ensure_ascii=False),
        timestamp=utc_now_naive(),
    ))


@router.get("/categories", response_model=List[str])
async def list_inventory_categories(
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_inventory")),
):
    """Return this pharmacy's category names: the categories table (with or without
    products) plus any text still carried by a product but missing from the table."""
    pharmacy_id = ctx["pharmacy_id"]
    table_names = (await db.execute(
        select(Category.name).where(Category.pharmacy_id == pharmacy_id)
    )).scalars().all()
    used_names = (await db.execute(
        select(InventoryItem.category)
        .where(
            InventoryItem.pharmacy_id == pharmacy_id,
            InventoryItem.category.is_not(None),
            InventoryItem.category != "",
        )
        .distinct()
    )).scalars().all()
    merged: dict = {}
    for name in list(table_names) + list(used_names):
        if name and name.strip():
            merged.setdefault(name.strip().lower(), name.strip())
    return sorted(merged.values(), key=lambda value: (value.lower(), value))


@router.get("/categories/details", response_model=List[CategoryDetailResponse])
async def list_category_details(
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_inventory")),
):
    """Categories with their product counts, including categories with no product."""
    pharmacy_id = ctx["pharmacy_id"]
    rows = (await db.execute(
        select(Category).where(Category.pharmacy_id == pharmacy_id)
    )).scalars().all()
    counts = dict((await db.execute(
        select(func.lower(InventoryItem.category), func.count(InventoryItem.id))
        .where(InventoryItem.pharmacy_id == pharmacy_id, InventoryItem.category.is_not(None))
        .group_by(func.lower(InventoryItem.category))
    )).all())
    details = [
        CategoryDetailResponse(id=row.id, name=row.name, item_count=int(counts.get(row.name.lower(), 0)))
        for row in rows
    ]
    return sorted(details, key=lambda value: (value.name.lower(), value.name))


@router.post("/categories", response_model=CategoryMutationResponse)
async def create_category(
    req: CategoryNamePayload,
    db:  AsyncSession = Depends(get_db),
    ctx: dict         = Depends(require_permission("manage_inventory")),
):
    """Creates a category on its own, without any product."""
    pharmacy_id = ctx["pharmacy_id"]
    name = _clean_category_name(req.name)
    if name is None:
        raise HTTPException(status_code=422, detail="Category name cannot be blank.")
    if await _find_category(db, pharmacy_id, name):
        raise HTTPException(status_code=409, detail="A category with this name already exists.")
    category = Category(pharmacy_id=pharmacy_id, name=name, created_at=utc_now_naive())
    db.add(category)
    try:
        await db.flush()
        await _audit_category(db, ctx, "CREATE_CATEGORY", str(category.id), {"name": name})
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A category with this name already exists.") from exc
    return {
        "success": True,
        "message": f"Category '{name}' created.",
        "category": CategoryDetailResponse(id=category.id, name=name, item_count=0),
        "affected_items": 0,
    }


@router.patch("/categories/{category_id}", response_model=CategoryMutationResponse)
async def rename_category(
    category_id: int,
    req: CategoryNamePayload,
    db:  AsyncSession = Depends(get_db),
    ctx: dict         = Depends(require_permission("manage_inventory")),
):
    """Renames a category and every product that carries it."""
    pharmacy_id = ctx["pharmacy_id"]
    new_name = _clean_category_name(req.name)
    if new_name is None:
        raise HTTPException(status_code=422, detail="Category name cannot be blank.")
    category = (await db.execute(
        select(Category)
        .where(Category.id == category_id, Category.pharmacy_id == pharmacy_id)
        .with_for_update()
    )).scalars().first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found.")
    if await _find_category(db, pharmacy_id, new_name, exclude_id=category_id):
        raise HTTPException(status_code=409, detail="A category with this name already exists.")

    old_name = category.name
    affected = 0
    if new_name != old_name:
        category.name = new_name
        try:
            await db.flush()
            result = await db.execute(
                update(InventoryItem)
                .where(
                    InventoryItem.pharmacy_id == pharmacy_id,
                    func.lower(InventoryItem.category) == old_name.lower(),
                )
                .values(category=new_name)
            )
            affected = int(result.rowcount or 0)
            await _audit_category(db, ctx, "RENAME_CATEGORY", str(category.id), {
                "previous_name": old_name, "name": new_name, "affected_items": affected,
            })
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(status_code=409, detail="A category with this name already exists.") from exc
    return {
        "success": True,
        "message": f"Category renamed to '{new_name}'.",
        "category": CategoryDetailResponse(id=category.id, name=new_name, item_count=affected),
        "affected_items": affected,
    }


@router.delete("/categories/{category_id}", response_model=CategoryMutationResponse)
async def delete_category(
    category_id: int,
    db:  AsyncSession = Depends(get_db),
    ctx: dict         = Depends(require_permission("manage_inventory")),
):
    """Deletes a category. Its products stay and simply have no category."""
    pharmacy_id = ctx["pharmacy_id"]
    category = (await db.execute(
        select(Category)
        .where(Category.id == category_id, Category.pharmacy_id == pharmacy_id)
        .with_for_update()
    )).scalars().first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found.")
    name = category.name
    result = await db.execute(
        update(InventoryItem)
        .where(
            InventoryItem.pharmacy_id == pharmacy_id,
            func.lower(InventoryItem.category) == name.lower(),
        )
        .values(category=None)
    )
    affected = int(result.rowcount or 0)
    await _audit_category(db, ctx, "DELETE_CATEGORY", str(category.id), {"name": name, "affected_items": affected})
    await db.delete(category)
    await db.commit()
    return {
        "success": True,
        "message": f"Category '{name}' deleted.",
        "category": None,
        "affected_items": affected,
    }


@router.get("/summary", response_model=InventorySummaryResponse)
async def inventory_summary(
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_inventory")),
):
    """Aggregate only this pharmacy's stock and expose incomplete cost coverage."""
    result = await db.execute(
        select(
            func.count(InventoryItem.id),
            func.coalesce(func.sum(InventoryItem.stock_qty), 0.0),
            func.coalesce(func.sum(InventoryItem.stock_qty * InventoryItem.unit_sell_price), 0.0),
            func.coalesce(func.sum(InventoryItem.stock_qty * InventoryItem.unit_buy_price), 0.0),
            func.coalesce(func.sum(case(
                (and_(InventoryItem.stock_qty > 0, InventoryItem.unit_buy_price <= 0), 1),
                else_=0,
            )), 0),
        ).where(InventoryItem.pharmacy_id == ctx["pharmacy_id"])
    )
    item_count, total_units, selling_value, cost_value, missing_cost_count = result.one()
    cost_complete = int(missing_cost_count) == 0
    return {
        "item_count": int(item_count),
        "total_units": float(total_units),
        "potential_sales_value": round_money(selling_value),
        "stock_cost_value": round_money(cost_value) if cost_complete else None,
        "stock_cost_value_complete": cost_complete,
    }


@router.get("/items", response_model=List[InventoryItemResponse])
async def list_inventory(
    search:   Optional[str] = None,
    category: Optional[str] = None,
    # Optional paging. Without `limit` the whole catalog is returned, as before: the
    # catalog, overview and duplicate-scan screens need every row.
    limit:    Optional[int] = Query(None, ge=1, le=1000),
    offset:   int           = Query(0, ge=0, le=100000),
    db:       AsyncSession  = Depends(get_db),
    ctx:      dict          = Depends(require_permission("view_inventory")),
):
    """Lists inventory items scoped strictly to the authenticated pharmacy."""
    pharmacy_id = ctx["pharmacy_id"]
    query = select(InventoryItem).where(InventoryItem.pharmacy_id == pharmacy_id)

    if search and search.strip():
        search_filter = _like_pattern(search.strip())
        query = query.where(
            or_(
                InventoryItem.name_ar.ilike(search_filter, escape="\\"),
                InventoryItem.name_en.ilike(search_filter, escape="\\"),
                InventoryItem.active_ingredient.ilike(search_filter, escape="\\"),
                InventoryItem.barcode.ilike(search_filter, escape="\\"),
            )
        )
    if category:
        query = query.where(InventoryItem.category == category)

    # The id breaks ties between equal names so pages never repeat or skip a row.
    query = query.order_by(InventoryItem.name_ar, InventoryItem.id)
    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/items/{item_id}", response_model=InventoryItemResponse)
async def get_inventory_item(
    item_id: int,
    db:      AsyncSession = Depends(get_db),
    ctx:     dict         = Depends(require_permission("view_inventory")),
):
    """Gets a specific inventory item belonging to the authenticated pharmacy."""
    result = await db.execute(
        select(InventoryItem).where(
            InventoryItem.id == item_id,
            InventoryItem.pharmacy_id == ctx["pharmacy_id"]
        )
    )
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="الدواء غير موجود في هذه الصيدلية.")
    return item


@router.get("/items/{item_id}/price-history", response_model=List[InventoryPriceHistoryResponse])
async def get_inventory_price_history(
    item_id: int,
    # Newest changes first; bounded so a long-lived product cannot return thousands of rows.
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_inventory")),
):
    item_result = await db.execute(select(InventoryItem.id).where(
        InventoryItem.id == item_id,
        InventoryItem.pharmacy_id == ctx["pharmacy_id"],
    ))
    if item_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Product not found in this pharmacy.")
    result = await db.execute(
        select(InventoryPriceHistory)
        .where(
            InventoryPriceHistory.item_id == item_id,
            InventoryPriceHistory.pharmacy_id == ctx["pharmacy_id"],
        )
        .order_by(InventoryPriceHistory.recorded_at.desc(), InventoryPriceHistory.id.desc())
        .limit(limit)
    )
    return [{
        "id": row.id,
        "previous_unit_buy_price": row.previous_unit_buy_price,
        "previous_unit_sell_price": row.previous_unit_sell_price,
        "unit_buy_price": row.unit_buy_price,
        "unit_sell_price": row.unit_sell_price,
        "changed_by": row.changed_by,
        "recorded_at": row.recorded_at.isoformat() + "Z" if row.recorded_at else None,
    } for row in result.scalars().all()]


@router.get("/items/{item_id}/batches", response_model=List[InventoryBatchResponse])
async def get_inventory_item_batches(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("view_inventory")),
):
    item_result = await db.execute(select(InventoryItem.id).where(
        InventoryItem.id == item_id,
        InventoryItem.pharmacy_id == ctx["pharmacy_id"],
    ))
    if item_result.scalar_one_or_none() is None:
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
        "unit_buy_price": row.unit_buy_price,
        "unit_sell_price": row.unit_sell_price,
        "expiry_date": row.expiry_date,
        "total_cost": round_money(row.quantity * row.unit_buy_price),
        "total_retail": round_money(row.quantity * row.unit_sell_price),
        "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
    } for row in result.scalars().all()]



@router.get("/low-stock", response_model=List[InventoryItemResponse])
async def list_low_stock(
    # Lowest stock first; bounded (the default covers any realistic pharmacy).
    limit: int          = Query(500, ge=1, le=1000),
    db:  AsyncSession = Depends(get_db),
    ctx: dict         = Depends(require_permission("view_inventory")),
):
    """Lists low stock items scoped strictly to the authenticated pharmacy."""
    result = await db.execute(
        select(InventoryItem)
        .where(
            InventoryItem.pharmacy_id == ctx["pharmacy_id"],
            InventoryItem.stock_qty <= InventoryItem.min_threshold
        )
        .order_by(InventoryItem.stock_qty, InventoryItem.id)
        .limit(limit)
    )
    return result.scalars().all()


@router.post("/create", response_model=ProductMutationResponse)
async def create_product(
    req: ProductPayload,
    db:  AsyncSession = Depends(get_db),
    ctx: dict         = Depends(require_permission("manage_inventory")),
):
    """Creates a new product scoped to the caller's pharmacy."""
    pharmacy_id = ctx["pharmacy_id"]
    if not req.name_ar.strip() or not req.name_en.strip():
        raise HTTPException(status_code=422, detail="Product names cannot be blank.")
    barcode = req.barcode.strip() if req.barcode and req.barcode.strip() else None

    # Check barcode uniqueness within this pharmacy
    if barcode:
        existing = await db.execute(
            select(InventoryItem).where(
                InventoryItem.barcode == barcode,
                InventoryItem.pharmacy_id == pharmacy_id
            )
        )
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail="الباركود مسجل بالفعل لصنف آخر في صيدليتك.")

    category_name = await _ensure_category(db, pharmacy_id, req.category)

    item = InventoryItem(
        pharmacy_id=pharmacy_id,
        barcode=barcode,
        name_ar=req.name_ar.strip(),
        name_en=req.name_en.strip(),
        active_ingredient=req.active_ingredient.strip() if req.active_ingredient else None,
        category=category_name,
        stock_qty=max(0.0, req.stock_qty),
        min_threshold=max(1.0, req.min_threshold),
        unit_buy_price=max(0.0, req.unit_buy_price),
        unit_sell_price=max(0.0, req.unit_sell_price),
        expiry_date=req.expiry_date,
        created_at=utc_now_naive()
    )
    db.add(item)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if barcode:
            raise HTTPException(status_code=409, detail="الباركود مسجل بالفعل لصنف آخر في صيدليتك.") from exc
        raise HTTPException(status_code=409, detail="The product could not be saved because of a data conflict.") from exc

    db.add(InventoryPriceHistory(
        pharmacy_id=pharmacy_id,
        item_id=item.id,
        previous_unit_buy_price=None,
        previous_unit_sell_price=None,
        unit_buy_price=item.unit_buy_price,
        unit_sell_price=item.unit_sell_price,
        changed_by=ctx["user_id"],
    ))

    if item.stock_qty > 0:
        db.add(InventoryBatch(
            pharmacy_id=pharmacy_id,
            item_id=item.id,
            batch_number=req.batch_number.strip() if req.batch_number and req.batch_number.strip() else None,
            quantity=item.stock_qty,
            unit_buy_price=item.unit_buy_price,
            unit_sell_price=item.unit_sell_price,
            expiry_date=item.expiry_date,
            created_at=utc_now_naive(),
            updated_at=utc_now_naive(),
        ))
        await sync_item_expiry(db, pharmacy_id, item)

    # Log to audit trail with authentic user & pharmacy context
    user_res = await db.execute(select(User).where(User.id == ctx["user_id"]))
    user_obj = user_res.scalars().first()
    user_name = user_obj.name if user_obj else f"User #{ctx['user_id']}"

    audit = AuditLog(
        pharmacy_id=pharmacy_id,
        action_type="CREATE_PRODUCT",
        entity_type="inventory_item",
        entity_id=str(item.id),
        user_id=ctx["user_id"],
        user_name=user_name,
        user_role=ctx["role"],
        details_json=json.dumps({
            "role_name": ctx.get("role_name"),
            "name_ar": item.name_ar,
            "stock_qty": item.stock_qty,
            "unit_sell_price": item.unit_sell_price
        }, ensure_ascii=False),
        timestamp=utc_now_naive()
    )
    db.add(audit)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if barcode:
            raise HTTPException(status_code=409, detail="الباركود مسجل بالفعل لصنف آخر في صيدليتك.") from exc
        raise HTTPException(status_code=409, detail="The product could not be saved because of a data conflict.") from exc
    await db.refresh(item)

    return {
        "success": True,
        "message": f"تمت إضافة الدواء '{item.name_ar}' إلى مخزن الصيدلية بنجاح.",
        "item": item
    }


@router.put("/items/{item_id}", response_model=ProductMutationResponse)
async def update_product(
    item_id: int,
    req:     ProductUpdatePayload,
    db:      AsyncSession = Depends(get_db),
    ctx:     dict         = Depends(require_permission("manage_inventory")),
):
    """Updates an existing product in the caller's pharmacy."""
    pharmacy_id = ctx["pharmacy_id"]

    result = await db.execute(
        select(InventoryItem).where(
            InventoryItem.id == item_id,
            InventoryItem.pharmacy_id == pharmacy_id
        )
    )
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="الدواء غير موجود في صيدليتك.")
    if not req.name_ar.strip() or not req.name_en.strip():
        raise HTTPException(status_code=422, detail="Product names cannot be blank.")
    if req.stock_qty is not None and req.stock_qty != item.stock_qty:
        raise HTTPException(
            status_code=409,
            detail="Stock quantity can only change through a confirmed stock movement.",
        )

    previous_unit_buy_price = item.unit_buy_price
    previous_unit_sell_price = item.unit_sell_price

    # Check barcode conflict
    barcode = req.barcode.strip() if req.barcode and req.barcode.strip() else None
    if barcode and barcode != item.barcode:
        existing = await db.execute(
            select(InventoryItem).where(
                InventoryItem.barcode == barcode,
                InventoryItem.pharmacy_id == pharmacy_id,
                InventoryItem.id != item_id
            )
        )
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail="الباركود الجديد مسجل بالفعل لصنف آخر.")

    item.name_ar           = req.name_ar.strip()
    item.name_en           = req.name_en.strip()
    item.active_ingredient = req.active_ingredient.strip() if req.active_ingredient else None
    item.category          = await _ensure_category(db, pharmacy_id, req.category)
    item.min_threshold     = max(1.0, req.min_threshold)
    item.unit_buy_price    = max(0.0, req.unit_buy_price)
    item.unit_sell_price   = max(0.0, req.unit_sell_price)
    if "barcode" in req.model_fields_set:
        item.barcode = barcode
    await apply_typed_expiry(db, pharmacy_id, item, req.expiry_date)

    price_changed = (
        previous_unit_buy_price != item.unit_buy_price
        or previous_unit_sell_price != item.unit_sell_price
    )
    if price_changed:
        db.add(InventoryPriceHistory(
            pharmacy_id=pharmacy_id,
            item_id=item.id,
            previous_unit_buy_price=previous_unit_buy_price,
            previous_unit_sell_price=previous_unit_sell_price,
            unit_buy_price=item.unit_buy_price,
            unit_sell_price=item.unit_sell_price,
            changed_by=ctx["user_id"],
        ))

    # Audit log
    user_res = await db.execute(select(User).where(User.id == ctx["user_id"]))
    user_obj = user_res.scalars().first()
    user_name = user_obj.name if user_obj else f"User #{ctx['user_id']}"

    audit = AuditLog(
        pharmacy_id=pharmacy_id,
        action_type="UPDATE_PRODUCT",
        entity_type="inventory_item",
        entity_id=str(item.id),
        user_id=ctx["user_id"],
        user_name=user_name,
        user_role=ctx["role"],
        details_json=json.dumps({
            "role_name": ctx.get("role_name"),
            "name_ar": item.name_ar,
            "previous_unit_buy_price": previous_unit_buy_price,
            "unit_buy_price": item.unit_buy_price,
            "previous_unit_sell_price": previous_unit_sell_price,
            "unit_sell_price": item.unit_sell_price,
            "price_changed": price_changed,
        }, ensure_ascii=False),
        timestamp=utc_now_naive()
    )
    db.add(audit)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if barcode:
            raise HTTPException(status_code=409, detail="الباركود الجديد مسجل بالفعل لصنف آخر.") from exc
        raise HTTPException(status_code=409, detail="The product could not be saved because of a data conflict.") from exc
    await db.refresh(item)

    return {
        "success": True,
        "message": f"تم تحديث بيانات الدواء '{item.name_ar}' بنجاح.",
        "item": item
    }


class ItemCategoryPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    category: str = Field(min_length=1, max_length=40)


@router.patch("/items/{item_id}/category", response_model=ProductMutationResponse)
async def set_item_category(
    item_id: int,
    req:     ItemCategoryPayload,
    db:      AsyncSession = Depends(get_db),
    ctx:     dict         = Depends(require_permission("manage_inventory")),
):
    """Sets only the category of one product in the caller's pharmacy.

    Assigning a name that has no category row yet creates the row. If the
    pharmacy already has the same name in a different letter case, the existing
    spelling is reused so the categories list never splits into near-duplicates.
    Categories can also be created on their own (POST /categories).
    """
    pharmacy_id = ctx["pharmacy_id"]
    name = " ".join(req.category.split())
    if not name:
        raise HTTPException(status_code=422, detail="Category name cannot be blank.")

    result = await db.execute(
        select(InventoryItem)
        .where(InventoryItem.id == item_id, InventoryItem.pharmacy_id == pharmacy_id)
        .with_for_update()
    )
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="الدواء غير موجود في صيدليتك.")

    new_category = await _ensure_category(db, pharmacy_id, name)

    previous_category = item.category
    if previous_category != new_category:
        item.category = new_category

        user_res = await db.execute(select(User).where(User.id == ctx["user_id"]))
        user_obj = user_res.scalars().first()
        user_name = user_obj.name if user_obj else f"User #{ctx['user_id']}"
        db.add(AuditLog(
            pharmacy_id=pharmacy_id,
            action_type="SET_PRODUCT_CATEGORY",
            entity_type="inventory_item",
            entity_id=str(item.id),
            user_id=ctx["user_id"],
            user_name=user_name,
            user_role=ctx["role"],
            details_json=json.dumps({
                "role_name": ctx.get("role_name"),
                "name_ar": item.name_ar,
                "previous_category": previous_category,
                "category": new_category,
            }, ensure_ascii=False),
            timestamp=utc_now_naive(),
        ))
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(status_code=409, detail="The category could not be saved because of a data conflict.") from exc
        await db.refresh(item)

    return {
        "success": True,
        "message": f"تم تعيين الفئة '{new_category}' للدواء '{item.name_ar}'.",
        "item": item,
    }


@router.post("/match", response_model=InventoryMatchResponse, response_model_exclude_unset=True)
async def match_product(
    req: MatchProductRequest,
    db:  AsyncSession = Depends(get_db),
    ctx: dict         = Depends(require_permission("view_inventory")),
):
    """
    Looks for exact match or returns similar suggestions/alternatives scoped to current pharmacy.
    """
    pharmacy_id = ctx["pharmacy_id"]
    query_str = req.query_name.strip()
    if not query_str:
        # A blank query would become "%%" and report an arbitrary product as the match.
        return {"found": False, "query_name": "", "suggestions": []}

    # 1. Exact or strong partial match
    exact_res = await db.execute(
        select(InventoryItem).where(
            InventoryItem.pharmacy_id == pharmacy_id,
            or_(
                InventoryItem.name_ar.ilike(_like_pattern(query_str), escape="\\"),
                InventoryItem.name_en.ilike(_like_pattern(query_str), escape="\\")
            )
        )
    )
    matches = exact_res.scalars().all()
    if matches:
        return {
            "found": True,
            "matched_item": matches[0],
            "alternatives": matches[1:4]
        }

    # 2. Fuzzy match prefix
    prefix = query_str[:4] if len(query_str) >= 4 else query_str
    fuzzy_res = await db.execute(
        select(InventoryItem).where(
            InventoryItem.pharmacy_id == pharmacy_id,
            or_(
                InventoryItem.name_ar.ilike(_like_pattern(prefix), escape="\\"),
                InventoryItem.name_en.ilike(_like_pattern(prefix), escape="\\")
            )
        ).limit(3)
    )
    fuzzy_matches = fuzzy_res.scalars().all()

    return {
        "found": False,
        "query_name": query_str,
        "suggestions": fuzzy_matches,
        "message": f"الصنف '{query_str}' غير مسجل في الصيدلية. يمكنك إضافته الآن كصنف جديد أو اختيار بديل مشابه."
    }


class DirectRestockPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    quantity: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    unit_buy_price: Optional[MoneyIn] = Field(default=None, ge=0, le=100_000_000, allow_inf_nan=False)
    unit_sell_price: Optional[MoneyIn] = Field(default=None, gt=0, le=100_000_000, allow_inf_nan=False)
    batch_number: Optional[str] = Field(default=None, max_length=60)
    expiry_date: Optional[str] = Field(default=None, max_length=20)
    supplier_notes: Optional[str] = Field(default=None, max_length=500)
    # Free-text supplier name; groups the credit restocks on the payables screen.
    supplier_name: Optional[str] = Field(default=None, max_length=150)

    @field_validator("expiry_date")
    @classmethod
    def validate_expiry_date(cls, value: Optional[str]) -> Optional[str]:
        return _validate_expiry_date(value)


@router.post("/items/{item_id}/restock", response_model=RestockResponse)
async def restock_product(
    item_id: int,
    req: DirectRestockPayload,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("manage_inventory")),
):
    """Directly intakes inventory stock, updates quantities, and records ledger restock."""
    from server.app.db.models import LedgerEntry, LedgerEntryItem
    pharmacy_id = ctx["pharmacy_id"]

    res = await db.execute(
        select(InventoryItem).where(
            InventoryItem.id == item_id,
            InventoryItem.pharmacy_id == pharmacy_id
        ).with_for_update()
    )
    item = res.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="الدواء غير موجود في هذه الصيدلية.")

    old_stock = item.stock_qty
    previous_unit_buy_price = item.unit_buy_price
    previous_unit_sell_price = item.unit_sell_price
    item.stock_qty += req.quantity

    if req.unit_buy_price is not None and req.unit_buy_price > 0:
        item.unit_buy_price = req.unit_buy_price
    if req.unit_sell_price is not None and req.unit_sell_price > 0:
        item.unit_sell_price = req.unit_sell_price

    if (
        previous_unit_buy_price != item.unit_buy_price
        or previous_unit_sell_price != item.unit_sell_price
    ):
        db.add(InventoryPriceHistory(
            pharmacy_id=pharmacy_id,
            item_id=item.id,
            previous_unit_buy_price=previous_unit_buy_price,
            previous_unit_sell_price=previous_unit_sell_price,
            unit_buy_price=item.unit_buy_price,
            unit_sell_price=item.unit_sell_price,
            changed_by=ctx["user_id"],
        ))

    # Keep this restock's ledger and lot at the same purchase cost. An explicit
    # zero is a valid lot cost and must not inherit the product's older price.
    unit_cost = req.unit_buy_price if req.unit_buy_price is not None else (item.unit_buy_price or 0.0)
    total_cost = round_money(req.quantity * unit_cost)
    supplier_name = " ".join(req.supplier_name.split()) if req.supplier_name else None
    supplier_notes = " ".join(req.supplier_notes.split()) if req.supplier_notes else None

    # Record ledger entry for restock
    ledger = LedgerEntry(
        id=f"restock-{uuid.uuid4().hex}",
        pharmacy_id=pharmacy_id,
        entry_type="log_restock",
        total_amount=total_cost,
        payment_method="credit",
        notes=f"توريد مباشر لصنف {item.name_ar} (كمية: {req.quantity})" + (f" - دفعة {req.batch_number}" if req.batch_number else "") + (f" - ملاحظات المورد: {supplier_notes}" if supplier_notes else ""),
        supplier_name=supplier_name or None,
        created_by=ctx["user_id"],
        confirmed_by=ctx["user_id"],
        confirmed_at=utc_now_naive(),
    )
    db.add(ledger)
    await db.flush()

    db.add(LedgerEntryItem(
        entry_id=ledger.id,
        item_id=item.id,
        item_name=item.name_ar,
        quantity=req.quantity,
        unit_price=unit_cost,
        unit_cost=unit_cost,
        subtotal=total_cost,
    ))

    db.add(InventoryBatch(
        pharmacy_id=pharmacy_id,
        item_id=item.id,
        batch_number=req.batch_number.strip() if req.batch_number and req.batch_number.strip() else None,
        quantity=req.quantity,
        unit_buy_price=unit_cost,
        unit_sell_price=req.unit_sell_price if req.unit_sell_price is not None else item.unit_sell_price,
        # A lot only carries an expiry the user typed for it; it no longer
        # inherits the product's date (which now mirrors the earliest lot).
        expiry_date=req.expiry_date if req.expiry_date else None,
        created_at=utc_now_naive(),
        updated_at=utc_now_naive(),
    ))
    await sync_item_expiry(db, pharmacy_id, item)

    db.add(AuditLog(
        pharmacy_id=pharmacy_id,
        action_type="DIRECT_RESTOCK",
        entity_type="inventory_item",
        entity_id=str(item.id),
        user_id=ctx["user_id"],
        user_name=ctx.get("user_name"),
        user_role=ctx["role"],
        details_json=json.dumps({
            "role_name": ctx.get("role_name"),
            "added_qty": req.quantity,
            "old_stock": old_stock,
            "new_stock": item.stock_qty,
            "total_cost": total_cost,
            "batch_number": req.batch_number,
            "supplier_name": supplier_name or None,
        }, ensure_ascii=False),
        timestamp=utc_now_naive()
    ))

    await db.commit()
    await db.refresh(item)

    return {
        "success": True,
        "message": f"تمت إضافة {req.quantity} علبة للصنف '{item.name_ar}' بنجاح.",
        "item": item,
        "old_stock": old_stock,
        "new_stock": item.stock_qty,
        "total_cost": total_cost,
    }
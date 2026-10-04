# server/app/services/expiry.py
"""Keeps a product's catalog expiry date in step with its stock lots.

Rule (Waiting item 15, "earliest"): the catalog date is the earliest expiry
among lots that still have stock. A lot without an expiry is ignored. If no
lot with stock has an expiry, the date already on the product stays as it is.
Dates are YYYY-MM-DD strings, so plain string comparison orders them.
"""
from typing import Optional

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from server.app.db.models import InventoryBatch, InventoryItem


async def sync_item_expiry(db: AsyncSession, pharmacy_id: int, item: InventoryItem) -> None:
    """Set item.expiry_date to the earliest expiry among lots with stock.

    Call after any change to lots (create, restock, FIFO sale). The session is
    created with autoflush=False, so pending lot changes are NOT visible to a
    query until they are flushed. We flush first, otherwise the min() below
    reads stale quantities and dates.
    """
    await db.flush()
    result = await db.execute(
        select(func.min(InventoryBatch.expiry_date)).where(
            InventoryBatch.item_id == item.id,
            InventoryBatch.pharmacy_id == pharmacy_id,
            InventoryBatch.quantity > 0,
            InventoryBatch.expiry_date.is_not(None),
            InventoryBatch.expiry_date != "",
        )
    )
    earliest: Optional[str] = result.scalar_one_or_none()
    if earliest and item.expiry_date != earliest:
        item.expiry_date = earliest


async def apply_typed_expiry(
    db: AsyncSession,
    pharmacy_id: int,
    item: InventoryItem,
    typed: Optional[str],
) -> None:
    """Apply an expiry typed on the product edit form.

    The catalog shows the earliest lot's date, so the field edits that lot:
    the in-stock lot that supplies the shown date, or, when no lot has a date,
    the oldest in-stock lot. With no lot in stock only the product changes.
    """
    if typed == item.expiry_date:
        return
    lots_result = await db.execute(
        select(InventoryBatch)
        .where(
            InventoryBatch.item_id == item.id,
            InventoryBatch.pharmacy_id == pharmacy_id,
            InventoryBatch.quantity > 0,
        )
        .order_by(InventoryBatch.created_at.asc(), InventoryBatch.id.asc())
        .with_for_update()
    )
    lots = lots_result.scalars().all()
    dated = [lot for lot in lots if lot.expiry_date]
    target = min(dated, key=lambda lot: lot.expiry_date) if dated else (lots[0] if lots else None)
    if target is not None:
        target.expiry_date = typed
    item.expiry_date = typed
    # sync_item_expiry flushes the lot edit before reading, so the typed date
    # is what the min() sees (not the old committed one).
    await sync_item_expiry(db, pharmacy_id, item)
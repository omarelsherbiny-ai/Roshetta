"""Pure inventory quantity checks shared by action processing and unit tests."""

from collections import defaultdict
from collections.abc import Iterable, Mapping


def overdrawn_inventory_quantities(
    lines: Iterable[tuple[int, float]],
    available_by_inventory: Mapping[int, float],
) -> dict[int, float]:
    """Return item IDs whose combined requested quantity exceeds current stock."""
    requested_by_inventory: dict[int, float] = defaultdict(float)
    for inventory_id, quantity in lines:
        requested_by_inventory[inventory_id] += quantity

    return {
        inventory_id: quantity
        for inventory_id, quantity in requested_by_inventory.items()
        if quantity > available_by_inventory.get(inventory_id, 0.0)
    }

# server/app/db/migrations.py
"""Small, ordered schema upgrades for databases created before Alembic was added.

New tables are created from SQLAlchemy metadata; this module handles changes to
existing tables that ``metadata.create_all`` deliberately does not apply.
"""
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection

# (table, column, precision, scale): the money columns changed by migration v15. Keep this
# list in step with the Money(...) columns in models/__init__.py.
MONEY_COLUMNS = (
    ("inventory", "unit_buy_price", 12, 2),
    ("inventory", "unit_sell_price", 12, 2),
    ("inventory_batches", "unit_buy_price", 12, 2),
    ("inventory_batches", "unit_sell_price", 12, 2),
    ("inventory_price_history", "previous_unit_buy_price", 12, 2),
    ("inventory_price_history", "previous_unit_sell_price", 12, 2),
    ("inventory_price_history", "unit_buy_price", 12, 2),
    ("inventory_price_history", "unit_sell_price", 12, 2),
    ("entries", "total_amount", 18, 2),
    ("entry_items", "unit_price", 12, 2),
    ("entry_items", "unit_cost", 18, 6),
    ("entry_items", "subtotal", 18, 2),
    ("restock_settlements", "amount", 18, 2),
)


async def upgrade_schema(connection: AsyncConnection) -> None:
    """Apply all idempotent schema upgrades before the application serves traffic."""
    await connection.run_sync(_upgrade_sync)


def _upgrade_sync(connection) -> None:
    inspector = inspect(connection)
    if "schema_migrations" not in inspector.get_table_names():
        connection.execute(text(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
        ))

    versions = {row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))}
    if 1 not in versions:
        inspector = inspect(connection)
        if "entry_items" in inspector.get_table_names():
            columns = {column["name"] for column in inspector.get_columns("entry_items")}
            if "unit_cost" not in columns:
                connection.execute(text("ALTER TABLE entry_items ADD COLUMN unit_cost FLOAT NULL"))
        connection.execute(text(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (1, CURRENT_TIMESTAMP)"
        ))

    if 2 not in versions:
        inspector = inspect(connection)
        if "prescriptions" in inspector.get_table_names():
            columns = {column["name"] for column in inspector.get_columns("prescriptions")}
            if "review_decision" not in columns:
                connection.execute(text("ALTER TABLE prescriptions ADD COLUMN review_decision VARCHAR(30) NULL"))
            if "review_notes" not in columns:
                connection.execute(text("ALTER TABLE prescriptions ADD COLUMN review_notes TEXT NULL"))
            if "reviewed_at" not in columns:
                connection.execute(text("ALTER TABLE prescriptions ADD COLUMN reviewed_at TIMESTAMP NULL"))
        connection.execute(text(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (2, CURRENT_TIMESTAMP)"
        ))

    if 3 not in versions:
        if connection.dialect.name == "postgresql" and "pharmacy_profile" in inspect(connection).get_table_names():
            connection.execute(text(
                "ALTER TABLE pharmacy_profile ALTER COLUMN invite_code TYPE VARCHAR(16)"
            ))
        connection.execute(text(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (3, CURRENT_TIMESTAMP)"
        ))

    if 4 not in versions:
        table_names = inspect(connection).get_table_names()
        if "inventory" in table_names:
            duplicate = connection.execute(text(
                "SELECT 1 FROM inventory "
                "WHERE pharmacy_id IS NOT NULL AND barcode IS NOT NULL "
                "GROUP BY pharmacy_id, barcode HAVING COUNT(*) > 1 LIMIT 1"
            )).first()
            if duplicate:
                raise RuntimeError(
                    "Cannot enforce pharmacy-scoped barcode uniqueness: resolve duplicate "
                    "barcodes within each pharmacy, then restart the migration."
                )
            indexes = {index["name"] for index in inspect(connection).get_indexes("inventory")}
            if "uq_inventory_pharmacy_barcode" not in indexes:
                connection.execute(text(
                    "CREATE UNIQUE INDEX uq_inventory_pharmacy_barcode "
                    "ON inventory (pharmacy_id, barcode) WHERE barcode IS NOT NULL"
                ))
        connection.execute(text(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (4, CURRENT_TIMESTAMP)"
        ))

    if 5 not in versions:
        if "stored_uploads" in inspect(connection).get_table_names():
            columns = {column["name"] for column in inspect(connection).get_columns("stored_uploads")}
            if "document_type" not in columns:
                connection.execute(text(
                    "ALTER TABLE stored_uploads ADD COLUMN document_type VARCHAR(30) "
                    "NOT NULL DEFAULT 'prescription'"
                ))
        connection.execute(text(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (5, CURRENT_TIMESTAMP)"
        ))

    if 6 not in versions:
        if "users" in inspect(connection).get_table_names():
            columns = {column["name"] for column in inspect(connection).get_columns("users")}
            if "location" not in columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN location VARCHAR(160) NULL"))
            if "photo_url" not in columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN photo_url VARCHAR(500) NULL"))
            if "birth_date" not in columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN birth_date VARCHAR(10) NULL"))
        connection.execute(text(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (6, CURRENT_TIMESTAMP)"
        ))

    if 7 not in versions:
        if "pharmacy_members" in inspect(connection).get_table_names():
            columns = {column["name"] for column in inspect(connection).get_columns("pharmacy_members")}
            if "custom_role_id" not in columns:
                connection.execute(text(
                    "ALTER TABLE pharmacy_members ADD COLUMN custom_role_id INTEGER NULL"
                ))
        connection.execute(text(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (7, CURRENT_TIMESTAMP)"
        ))

    if 8 not in versions:
        table_names = inspect(connection).get_table_names()
        if "pharmacy_ownership_slots" in table_names and "pharmacy_members" in table_names:
            owners = connection.execute(text(
                "SELECT user_id, pharmacy_id FROM pharmacy_members "
                "WHERE role = 'owner' AND is_active = :active ORDER BY user_id, joined_at, id"
            ), {"active": True}).all()

            # Keep valid existing assignments, discard stale/mismatched ones,
            # then fill each user's lowest free slot. This makes migration 8
            # safe to resume if an earlier deployment partially populated the
            # table and avoids reusing slot 1 for every pharmacy.
            active_owner_by_pharmacy = {pharmacy_id: user_id for user_id, pharmacy_id in owners}
            existing_slots = connection.execute(text(
                "SELECT id, user_id, pharmacy_id, slot_number FROM pharmacy_ownership_slots"
            )).all()
            used_slots: dict[int, set[int]] = {}
            assigned_pharmacies: set[int] = set()
            for slot_id, user_id, pharmacy_id, slot_number in existing_slots:
                if active_owner_by_pharmacy.get(pharmacy_id) != user_id or not 1 <= slot_number <= 5:
                    connection.execute(text(
                        "DELETE FROM pharmacy_ownership_slots WHERE id = :slot_id"
                    ), {"slot_id": slot_id})
                    continue
                used_slots.setdefault(user_id, set()).add(slot_number)
                assigned_pharmacies.add(pharmacy_id)

            for user_id, pharmacy_id in owners:
                if pharmacy_id in assigned_pharmacies:
                    continue
                occupied = used_slots.setdefault(user_id, set())
                available = sorted(set(range(1, 6)) - occupied)
                # Legacy accounts that already own more than five locations
                # keep their memberships; the API still blocks creating any
                # additional pharmacies using the active membership count.
                if not available:
                    continue
                slot_number = available[0]
                connection.execute(text(
                    "INSERT INTO pharmacy_ownership_slots (user_id, pharmacy_id, slot_number, created_at) "
                    "VALUES (:user_id, :pharmacy_id, :slot_number, CURRENT_TIMESTAMP)"
                ), {"user_id": user_id, "pharmacy_id": pharmacy_id, "slot_number": slot_number})
                occupied.add(slot_number)
                assigned_pharmacies.add(pharmacy_id)
        connection.execute(text(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (8, CURRENT_TIMESTAMP)"
        ))

    if 9 not in versions:
        for table_name in ("staff_shifts", "staff_compensation"):
            if table_name in inspect(connection).get_table_names():
                columns = {column["name"] for column in inspect(connection).get_columns(table_name)}
                if "is_active" not in columns:
                    connection.execute(text(
                        f"ALTER TABLE {table_name} ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"
                    ))
        connection.execute(text(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (9, CURRENT_TIMESTAMP)"
        ))

    if 10 not in versions:
        inspector = inspect(connection)
        table_names = inspector.get_table_names()
        if "inventory_batches" not in table_names:
            pk_type = "SERIAL PRIMARY KEY" if connection.dialect.name == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
            connection.execute(text(f"""
                CREATE TABLE inventory_batches (
                    id {pk_type},
                    pharmacy_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    batch_number VARCHAR(60) NULL,
                    quantity FLOAT NOT NULL DEFAULT 0.0,
                    unit_buy_price FLOAT NOT NULL DEFAULT 0.0,
                    unit_sell_price FLOAT NOT NULL DEFAULT 0.0,
                    expiry_date VARCHAR(20) NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (pharmacy_id) REFERENCES pharmacy_profile (id),
                    FOREIGN KEY (item_id) REFERENCES inventory (id) ON DELETE CASCADE
                )
            """))
            connection.execute(text("CREATE INDEX ix_inventory_batches_pharmacy_id ON inventory_batches (pharmacy_id)"))
            connection.execute(text("CREATE INDEX ix_inventory_batches_item_id ON inventory_batches (item_id)"))

        if "inventory" in table_names:
            connection.execute(text("""
                INSERT INTO inventory_batches (pharmacy_id, item_id, batch_number, quantity, unit_buy_price, unit_sell_price, expiry_date, created_at, updated_at)
                SELECT i.pharmacy_id, i.id, 'BATCH-INIT', i.stock_qty, i.unit_buy_price, i.unit_sell_price, i.expiry_date, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                FROM inventory i
                WHERE i.stock_qty > 0 AND i.pharmacy_id IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM inventory_batches b WHERE b.item_id = i.id
                )
            """))

        connection.execute(text(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (10, CURRENT_TIMESTAMP)"
        ))

    if 11 not in versions:
        if "pharmacy_profile" in inspect(connection).get_table_names():
            columns = {column["name"] for column in inspect(connection).get_columns("pharmacy_profile")}
            if "invite_code" in columns:
                connection.execute(text("UPDATE pharmacy_profile SET invite_code = NULL"))
        connection.execute(text(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (11, CURRENT_TIMESTAMP)"
        ))

    if 12 not in versions:
        # Supplier payables (Session 40). The applied_at written here is the day payables
        # tracking starts, so restocks made before it are not counted as debt. The
        # restock_settlements table is built by metadata.create_all.
        if "entries" in inspect(connection).get_table_names():
            columns = {column["name"] for column in inspect(connection).get_columns("entries")}
            if "supplier_name" not in columns:
                connection.execute(text("ALTER TABLE entries ADD COLUMN supplier_name VARCHAR(150) NULL"))
        connection.execute(text(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (12, CURRENT_TIMESTAMP)"
        ))

    if 13 not in versions:
        # Categories that can exist without a product (Session 78). The table is created
        # here when missing (same shape as the Category model) and filled from the category
        # text already stored on products. On a normal start metadata.create_all has already
        # made the table and its index before this runs, so every step must be repeatable.
        table_names = inspect(connection).get_table_names()
        if "categories" not in table_names:
            pk_type = "SERIAL PRIMARY KEY" if connection.dialect.name == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
            connection.execute(text(f"""
                CREATE TABLE categories (
                    id {pk_type},
                    pharmacy_id INTEGER NOT NULL,
                    name VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (pharmacy_id) REFERENCES pharmacy_profile (id)
                )
            """))
            connection.execute(text("CREATE INDEX ix_categories_pharmacy_id ON categories (pharmacy_id)"))
        # No inspector check here: SQLAlchemy cannot reflect an expression index, and
        # metadata.create_all may already have created this table and its index.
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_categories_pharmacy_name ON categories (pharmacy_id, lower(name))"
        ))
        if "inventory" in table_names:
            connection.execute(text("""
                INSERT INTO categories (pharmacy_id, name, created_at)
                SELECT pharmacy_id, MIN(TRIM(category)), CURRENT_TIMESTAMP
                FROM inventory
                WHERE pharmacy_id IS NOT NULL AND category IS NOT NULL AND TRIM(category) <> ''
                AND NOT EXISTS (
                    SELECT 1 FROM categories c
                    WHERE c.pharmacy_id = inventory.pharmacy_id
                    AND lower(c.name) = lower(TRIM(inventory.category))
                )
                GROUP BY pharmacy_id, lower(TRIM(category))
            """))
        connection.execute(text(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (13, CURRENT_TIMESTAMP)"
        ))

    if 14 not in versions:
        # Sign-out of every session after a PIN change (Session 111, debt 22).
        if "users" in inspect(connection).get_table_names():
            columns = {column["name"] for column in inspect(connection).get_columns("users")}
            if "tokens_valid_after" not in columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN tokens_valid_after TIMESTAMP NULL"))
        connection.execute(text(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (14, CURRENT_TIMESTAMP)"
        ))

    if 15 not in versions:
        # Money as exact NUMERIC (debt 6, Session 113). PostgreSQL: the columns change type and
        # existing values are rounded. SQLite cannot change a column type, and its numeric
        # affinity stores whatever it is given, so only the stored values are rounded there;
        # the Money column type rounds every new write on both databases. Every step can run
        # again (a new database already has the final types).
        table_names = inspect(connection).get_table_names()
        for table, column, precision, scale in MONEY_COLUMNS:
            if table not in table_names:
                continue
            columns = {c["name"] for c in inspect(connection).get_columns(table)}
            if column not in columns:
                continue
            if connection.dialect.name == "postgresql":
                connection.execute(text(
                    f"ALTER TABLE {table} ALTER COLUMN {column} TYPE NUMERIC({precision}, {scale}) "
                    f"USING ROUND({column}::numeric, {scale})"
                ))
            else:
                connection.execute(text(
                    f"UPDATE {table} SET {column} = ROUND({column}, {scale}) WHERE {column} IS NOT NULL"
                ))
        connection.execute(text(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (15, CURRENT_TIMESTAMP)"
        ))
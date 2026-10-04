# tests/test_migrations.py
"""Regression tests for restart-safe existing-database migrations."""

import unittest

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from server.app.db.migrations import _upgrade_sync


class OwnershipSlotMigrationTests(unittest.TestCase):
    def test_migration_preserves_assignments_and_fills_free_slots_without_collisions(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO schema_migrations (version, applied_at) "
                "VALUES (1, CURRENT_TIMESTAMP), (2, CURRENT_TIMESTAMP), "
                "(3, CURRENT_TIMESTAMP), (4, CURRENT_TIMESTAMP), "
                "(5, CURRENT_TIMESTAMP), (6, CURRENT_TIMESTAMP), (7, CURRENT_TIMESTAMP)"
            ))
            connection.execute(text(
                "CREATE TABLE pharmacy_members (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "pharmacy_id INTEGER NOT NULL, role VARCHAR(20), is_active BOOLEAN, joined_at TIMESTAMP)"
            ))
            connection.execute(text(
                "CREATE TABLE pharmacy_ownership_slots (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "pharmacy_id INTEGER NOT NULL, slot_number INTEGER NOT NULL, created_at TIMESTAMP, "
                "UNIQUE(user_id, slot_number), UNIQUE(pharmacy_id))"
            ))
            connection.execute(text(
                "CREATE TABLE staff_shifts (id INTEGER PRIMARY KEY, pharmacy_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL)"
            ))
            connection.execute(text(
                "CREATE TABLE staff_compensation (id INTEGER PRIMARY KEY, pharmacy_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO pharmacy_members (id, user_id, pharmacy_id, role, is_active, joined_at) VALUES "
                "(1, 10, 101, 'owner', 1, CURRENT_TIMESTAMP), "
                "(2, 10, 102, 'owner', 1, CURRENT_TIMESTAMP), "
                "(3, 10, 103, 'owner', 1, CURRENT_TIMESTAMP), "
                "(4, 20, 201, 'owner', 1, CURRENT_TIMESTAMP)"
            ))
            connection.execute(text(
                "INSERT INTO pharmacy_ownership_slots (id, user_id, pharmacy_id, slot_number, created_at) VALUES "
                "(1, 10, 101, 2, CURRENT_TIMESTAMP), "
                "(2, 10, 102, 1, CURRENT_TIMESTAMP), "
                "(3, 99, 999, 4, CURRENT_TIMESTAMP)"
            ))

            _upgrade_sync(connection)

            assignments = connection.execute(text(
                "SELECT user_id, pharmacy_id, slot_number FROM pharmacy_ownership_slots "
                "ORDER BY user_id, slot_number"
            )).all()
            self.assertEqual(assignments, [(10, 102, 1), (10, 101, 2), (10, 103, 3), (20, 201, 1)])
            applied = connection.execute(text(
                "SELECT version FROM schema_migrations WHERE version = 8"
            )).first()
            self.assertIsNotNone(applied)

            for table_name in ("staff_shifts", "staff_compensation"):
                columns = {column["name"] for column in inspect(connection).get_columns(table_name)}
                self.assertIn("is_active", columns)

            # Startup may rerun migrations on every process restart.
            _upgrade_sync(connection)
            self.assertEqual(connection.execute(text(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = 9"
            )).scalar_one(), 1)
        engine.dispose()


class BarcodeUniquenessMigrationTests(unittest.TestCase):
    @staticmethod
    def make_legacy_database():
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO schema_migrations (version, applied_at) "
                "VALUES (1, CURRENT_TIMESTAMP), (2, CURRENT_TIMESTAMP), (3, CURRENT_TIMESTAMP)"
            ))
            connection.execute(text(
                "CREATE TABLE inventory (id INTEGER PRIMARY KEY, pharmacy_id INTEGER, "
                "barcode VARCHAR(100), category VARCHAR(50), "
                "stock_qty FLOAT NOT NULL DEFAULT 0, unit_buy_price FLOAT NOT NULL DEFAULT 0, "
                "unit_sell_price FLOAT NOT NULL DEFAULT 0, expiry_date VARCHAR(20))"
            ))
        return engine

    def test_v4_stops_before_recording_migration_when_a_pharmacy_has_duplicate_barcodes(self):
        engine = self.make_legacy_database()
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO inventory (id, pharmacy_id, barcode) VALUES "
                "(1, 10, '123'), (2, 10, '123')"
            ))
            with self.assertRaisesRegex(RuntimeError, "resolve duplicate barcodes"):
                _upgrade_sync(connection)
            self.assertIsNone(connection.execute(text(
                "SELECT version FROM schema_migrations WHERE version = 4"
            )).first())
        engine.dispose()

    def test_v4_allows_null_and_cross_pharmacy_barcodes_but_rejects_local_duplicates(self):
        engine = self.make_legacy_database()
        with engine.begin() as connection:
            _upgrade_sync(connection)
            connection.execute(text(
                "INSERT INTO inventory (id, pharmacy_id, barcode) VALUES "
                "(1, 10, '123'), (2, 20, '123'), (3, 10, NULL), (4, 10, NULL)"
            ))
            with self.assertRaises(IntegrityError):
                connection.execute(text(
                    "INSERT INTO inventory (id, pharmacy_id, barcode) VALUES (5, 10, '123')"
                ))
        engine.dispose()


class InventoryBatchMigrationTests(unittest.TestCase):
    def test_v10_backfills_legacy_stock_once_and_preserves_lot_costs(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO schema_migrations (version, applied_at) VALUES "
                + ", ".join(f"({version}, CURRENT_TIMESTAMP)" for version in range(1, 10))
            ))
            connection.execute(text(
                "CREATE TABLE inventory (id INTEGER PRIMARY KEY, pharmacy_id INTEGER, category VARCHAR(50), "
                "stock_qty FLOAT NOT NULL DEFAULT 0, unit_buy_price FLOAT NOT NULL DEFAULT 0, "
                "unit_sell_price FLOAT NOT NULL DEFAULT 0, expiry_date VARCHAR(20))"
            ))
            connection.execute(text(
                "INSERT INTO inventory (id, pharmacy_id, stock_qty, unit_buy_price, unit_sell_price, expiry_date) "
                "VALUES (1, 10, 6, 2.5, 4.0, '2027-06-01'), "
                "(2, 10, 0, 3.0, 5.0, NULL), (3, NULL, 8, 1.0, 2.0, NULL)"
            ))

            _upgrade_sync(connection)

            batches = connection.execute(text(
                "SELECT pharmacy_id, item_id, batch_number, quantity, unit_buy_price, unit_sell_price, expiry_date "
                "FROM inventory_batches ORDER BY item_id"
            )).all()
            self.assertEqual(batches, [(10, 1, "BATCH-INIT", 6.0, 2.5, 4.0, "2027-06-01")])
            indexes = {index["name"] for index in inspect(connection).get_indexes("inventory_batches")}
            self.assertIn("ix_inventory_batches_pharmacy_id", indexes)
            self.assertIn("ix_inventory_batches_item_id", indexes)
            self.assertIsNotNone(connection.execute(text(
                "SELECT version FROM schema_migrations WHERE version = 10"
            )).first())

            _upgrade_sync(connection)
            self.assertEqual(connection.execute(text(
                "SELECT COUNT(*) FROM inventory_batches"
            )).scalar_one(), 1)
        engine.dispose()


class LegacyInvitationCodeMigrationTests(unittest.TestCase):
    def test_v11_clears_obsolete_codes_and_is_restart_safe(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO schema_migrations (version, applied_at) VALUES "
                + ", ".join(f"({version}, CURRENT_TIMESTAMP)" for version in range(1, 11))
            ))
            connection.execute(text(
                "CREATE TABLE pharmacy_profile (id INTEGER PRIMARY KEY, invite_code VARCHAR(16) NULL)"
            ))
            connection.execute(text(
                "INSERT INTO pharmacy_profile (id, invite_code) VALUES (1, 'OLD-CODE'), (2, NULL)"
            ))

            _upgrade_sync(connection)
            self.assertEqual(connection.execute(text(
                "SELECT invite_code FROM pharmacy_profile ORDER BY id"
            )).all(), [(None,), (None,)])
            self.assertIsNotNone(connection.execute(text(
                "SELECT version FROM schema_migrations WHERE version = 11"
            )).first())

            connection.execute(text(
                "UPDATE pharmacy_profile SET invite_code = 'ANOTHER-OLD-CODE' WHERE id = 1"
            ))
            _upgrade_sync(connection)
            self.assertEqual(connection.execute(text(
                "SELECT invite_code FROM pharmacy_profile WHERE id = 1"
            )).scalar_one(), "ANOTHER-OLD-CODE")
        engine.dispose()

class SupplierPayablesMigrationTests(unittest.TestCase):
    @staticmethod
    def make_database(entries_sql):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO schema_migrations (version, applied_at) VALUES "
                + ", ".join(f"({version}, CURRENT_TIMESTAMP)" for version in range(1, 12))
            ))
            connection.execute(text(entries_sql))
        return engine

    def test_v12_adds_supplier_name_to_old_entries_once_and_keeps_rows(self):
        engine = self.make_database(
            "CREATE TABLE entries (id VARCHAR(50) PRIMARY KEY, entry_type VARCHAR(20) NOT NULL)"
        )
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO entries (id, entry_type) VALUES ('restock-1', 'log_restock')"))

            _upgrade_sync(connection)

            columns = {column["name"] for column in inspect(connection).get_columns("entries")}
            self.assertIn("supplier_name", columns)
            self.assertIsNone(connection.execute(text(
                "SELECT supplier_name FROM entries WHERE id = 'restock-1'"
            )).scalar_one())
            self.assertEqual(connection.execute(text(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = 12"
            )).scalar_one(), 1)
            # The applied_at of v12 is the payables tracking start date.
            self.assertIsNotNone(connection.execute(text(
                "SELECT applied_at FROM schema_migrations WHERE version = 12"
            )).scalar_one())

            _upgrade_sync(connection)
            self.assertEqual(connection.execute(text(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = 12"
            )).scalar_one(), 1)
        engine.dispose()

    def test_v12_leaves_a_new_database_that_already_has_the_column_alone(self):
        engine = self.make_database(
            "CREATE TABLE entries (id VARCHAR(50) PRIMARY KEY, entry_type VARCHAR(20) NOT NULL, "
            "supplier_name VARCHAR(150) NULL)"
        )
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO entries (id, entry_type, supplier_name) VALUES ('restock-2', 'log_restock', 'UCP')"
            ))
            _upgrade_sync(connection)
            self.assertEqual(connection.execute(text(
                "SELECT supplier_name FROM entries WHERE id = 'restock-2'"
            )).scalar_one(), "UCP")
        engine.dispose()

    def test_v12_is_recorded_even_before_the_entries_table_exists(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            _upgrade_sync(connection)
            self.assertIsNotNone(connection.execute(text(
                "SELECT version FROM schema_migrations WHERE version = 12"
            )).first())
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
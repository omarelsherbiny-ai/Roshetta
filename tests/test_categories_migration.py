# tests/test_categories_migration.py
"""Migration 13: the categories table is created, filled from product text, and unique per pharmacy."""
import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from server.app.db.migrations import _upgrade_sync


def _legacy_database():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE pharmacy_profile (id INTEGER PRIMARY KEY)"))
        conn.execute(text(
            "CREATE TABLE inventory (id INTEGER PRIMARY KEY, pharmacy_id INTEGER, barcode VARCHAR(50), "
            "category VARCHAR(50), stock_qty FLOAT DEFAULT 0, unit_buy_price FLOAT DEFAULT 0, "
            "unit_sell_price FLOAT DEFAULT 0, expiry_date VARCHAR(20))"
        ))
        conn.execute(text("INSERT INTO pharmacy_profile (id) VALUES (1), (2)"))
        rows = [
            (1, "Pain"), (1, "pain "), (1, "Vitamins"), (1, None), (1, ""), (1, "   "),
            (2, "Pain"), (None, "Orphan"),
        ]
        for pharmacy_id, category in rows:
            conn.execute(
                text("INSERT INTO inventory (pharmacy_id, category) VALUES (:p, :c)"),
                {"p": pharmacy_id, "c": category},
            )
    return engine


class CategoriesMigrationTests(unittest.TestCase):
    def test_backfill_merges_case_variants_per_pharmacy_and_skips_blanks(self):
        engine = _legacy_database()
        with engine.begin() as conn:
            _upgrade_sync(conn)
            rows = conn.execute(text("SELECT pharmacy_id, lower(name) FROM categories ORDER BY 1, 2")).all()
        self.assertEqual([tuple(row) for row in rows], [(1, "pain"), (1, "vitamins"), (2, "pain")])

    def test_running_again_adds_nothing_and_version_is_recorded(self):
        engine = _legacy_database()
        with engine.begin() as conn:
            _upgrade_sync(conn)
        with engine.begin() as conn:
            _upgrade_sync(conn)
            count = conn.execute(text("SELECT COUNT(*) FROM categories")).scalar()
            version = conn.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = 13")).scalar()
        self.assertEqual(count, 3)
        self.assertEqual(version, 1)

    def test_names_are_unique_per_pharmacy_ignoring_case(self):
        engine = _legacy_database()
        with engine.begin() as conn:
            _upgrade_sync(conn)
        with self.assertRaises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO categories (pharmacy_id, name) VALUES (1, 'PAIN')"))
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO categories (pharmacy_id, name) VALUES (2, 'Vitamins')"))


    def test_table_and_index_already_made_by_create_all_do_not_break_the_migration(self):
        # Real startup order: metadata.create_all builds the table and its expression
        # index first, then the migration runs (this crashed the server in Session 78).
        engine = _legacy_database()
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE categories (id INTEGER PRIMARY KEY AUTOINCREMENT, pharmacy_id INTEGER NOT NULL, "
                "name VARCHAR(50) NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            ))
            conn.execute(text(
                "CREATE UNIQUE INDEX uq_categories_pharmacy_name ON categories (pharmacy_id, lower(name))"
            ))
        with engine.begin() as conn:
            _upgrade_sync(conn)
            rows = conn.execute(text("SELECT pharmacy_id, lower(name) FROM categories ORDER BY 1, 2")).all()
        self.assertEqual([tuple(row) for row in rows], [(1, "pain"), (1, "vitamins"), (2, "pain")])


if __name__ == "__main__":
    unittest.main()
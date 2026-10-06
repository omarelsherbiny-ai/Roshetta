# tests/test_money.py
"""Money handling (debt 6): rounding helpers, request rounding, the Money column type and migration v15."""

import unittest
from typing import Optional

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, func, select, text

from server.app.db.migrations import MONEY_COLUMNS, _upgrade_sync
from server.app.db.money import Money, MoneyIn, money_sum, round_money
from server.app.db.session import Base
import server.app.db.models  # noqa: F401  (registers every table on Base.metadata)


class RoundingHelperTests(unittest.TestCase):
    def test_half_up_on_the_decimal_text(self):
        self.assertEqual(round_money(10.005), 10.01)
        self.assertEqual(round_money(2.675), 2.68)  # Python's round() gives 2.67
        self.assertEqual(round_money(0.004), 0.0)
        self.assertEqual(round_money(1.999999, 6), 1.999999)
        self.assertIsNone(round_money(None))

    def test_sum_has_no_float_drift(self):
        self.assertEqual(money_sum([0.1] * 10), 1.0)
        self.assertEqual(money_sum([10.005, 10.005]), 20.02)  # each value is taken at 2 places first
        self.assertEqual(money_sum([None, 1.25]), 1.25)
        self.assertEqual(money_sum([0.1] * 100000), 10000.0)


class MoneyInputTests(unittest.TestCase):
    class Body(BaseModel):
        price: MoneyIn = Field(gt=0, le=100_000_000, allow_inf_nan=False)
        cost: Optional[MoneyIn] = Field(default=None, ge=0, allow_inf_nan=False)

    def test_fractional_prices_are_rounded_to_two_places(self):
        body = self.Body(price=10.005, cost="7.499")
        self.assertEqual(body.price, 10.01)
        self.assertEqual(body.cost, 7.5)

    def test_a_price_that_rounds_to_zero_is_refused(self):
        with self.assertRaises(ValidationError):
            self.Body(price=0.004)

    def test_nan_infinity_text_and_the_limit_are_still_refused(self):
        for bad in (float("nan"), float("inf"), "abc", 100_000_000.01):
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    self.Body(price=bad)

    def test_optional_stays_none(self):
        self.assertIsNone(self.Body(price=5).cost)


class MoneyColumnTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        metadata = MetaData()
        self.table = Table(
            "t", metadata,
            Column("id", Integer, primary_key=True),
            Column("amount", Money(18, 2)),
            Column("cost", Money(18, 6)),
        )
        metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_values_are_rounded_on_write_and_come_back_as_floats(self):
        with self.engine.begin() as connection:
            connection.execute(self.table.insert(), [{"id": 1, "amount": 10.005, "cost": 3.3333333}])
            row = connection.execute(select(self.table.c.amount, self.table.c.cost)).one()
        self.assertEqual(row[0], 10.01)
        self.assertIsInstance(row[0], float)
        self.assertEqual(row[1], 3.333333)

    def test_null_stays_null(self):
        with self.engine.begin() as connection:
            connection.execute(self.table.insert(), [{"id": 1, "amount": None, "cost": None}])
            self.assertEqual(tuple(connection.execute(select(self.table.c.amount, self.table.c.cost)).one()), (None, None))

    def test_sum_over_many_rows_is_exact(self):
        with self.engine.begin() as connection:
            connection.execute(self.table.insert(), [{"id": i, "amount": 0.1} for i in range(1, 3001)])
            total = connection.execute(select(func.coalesce(func.sum(self.table.c.amount), 0.0))).scalar_one()
        self.assertEqual(total, 300.0)

    def test_a_half_piaster_tolerance_is_not_rounded_up_inside_a_comparison(self):
        # The payables code compares Money columns with PAYABLE_EPS (0.005). As a bare Python float it
        # would be bound as a Money value and become 0.01; the typed Float literal must stay 0.005.
        from server.app.api.ledger import _SQL_EPS
        with self.engine.begin() as connection:
            connection.execute(self.table.insert(), [{"id": 1, "amount": 10.00, "cost": 9.99}])
            paid_in_full = connection.execute(
                select(self.table.c.id).where(self.table.c.cost >= self.table.c.amount - _SQL_EPS)
            ).first()
        self.assertIsNone(paid_in_full)  # 9.99 is a whole cent short of 10.00


class SchemaMatchesMigrationListTests(unittest.TestCase):
    def test_every_money_column_in_the_models_is_in_the_migration_list_and_back(self):
        in_models = {}
        for table in Base.metadata.sorted_tables:
            for column in table.columns:
                if isinstance(column.type, Money):
                    in_models[(table.name, column.name)] = (column.type.precision, column.type.scale)
        in_migration = {(t, c): (p, s) for t, c, p, s in MONEY_COLUMNS}
        self.assertEqual(in_models, in_migration)


class MoneyMigrationTests(unittest.TestCase):
    def make_database(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO schema_migrations (version, applied_at) VALUES "
                + ", ".join(f"({v}, CURRENT_TIMESTAMP)" for v in range(1, 15))
            ))
            connection.execute(text(
                "CREATE TABLE inventory (id INTEGER PRIMARY KEY, unit_buy_price FLOAT, unit_sell_price FLOAT)"
            ))
            connection.execute(text("CREATE TABLE entries (id VARCHAR(50) PRIMARY KEY, total_amount FLOAT NOT NULL)"))
            connection.execute(text(
                "CREATE TABLE entry_items (id INTEGER PRIMARY KEY, unit_price FLOAT, unit_cost FLOAT, subtotal FLOAT)"
            ))
            connection.execute(text("INSERT INTO inventory VALUES (1, 10.123456, 12.999999), (2, NULL, 5.0)"))
            connection.execute(text("INSERT INTO entries VALUES ('sale-1', 30.299999999999997)"))
            connection.execute(text("INSERT INTO entry_items VALUES (1, 10.1, 3.3333333333, 10.1), (2, 5.0, NULL, 5.0)"))
        return engine

    def test_v15_rounds_old_values_once_keeps_nulls_and_is_restart_safe(self):
        engine = self.make_database()
        with engine.begin() as connection:
            _upgrade_sync(connection)
            self.assertEqual(tuple(connection.execute(text(
                "SELECT unit_buy_price, unit_sell_price FROM inventory WHERE id = 1"
            )).one()), (10.12, 13.0))
            self.assertIsNone(connection.execute(text("SELECT unit_buy_price FROM inventory WHERE id = 2")).scalar_one())
            self.assertEqual(connection.execute(text("SELECT total_amount FROM entries")).scalar_one(), 30.3)
            # unit_cost keeps 6 places, the other item columns 2.
            self.assertEqual(connection.execute(text("SELECT unit_cost FROM entry_items WHERE id = 1")).scalar_one(), 3.333333)
            self.assertIsNone(connection.execute(text("SELECT unit_cost FROM entry_items WHERE id = 2")).scalar_one())
            self.assertEqual(connection.execute(text(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = 15"
            )).scalar_one(), 1)

            _upgrade_sync(connection)
            self.assertEqual(connection.execute(text(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = 15"
            )).scalar_one(), 1)
        engine.dispose()

    def test_v15_is_recorded_even_when_the_tables_do_not_exist_yet(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            _upgrade_sync(connection)
            self.assertIsNotNone(connection.execute(text(
                "SELECT version FROM schema_migrations WHERE version = 15"
            )).first())
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
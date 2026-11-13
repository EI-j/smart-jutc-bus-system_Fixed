import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from bus_system import database, fare_management
from bus_system.authentication import (
    authenticate,
    create_account,
    login_lockout_seconds,
)


class TestCommuterUpdates(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name) / "data"
        self.data_dir.mkdir()
        self.database_patch = patch.multiple(
            database,
            DATA_DIR=self.data_dir,
            DB_PATH=self.data_dir / "test.db",
        )
        self.database_patch.start()
        database.initialize_database()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def create_commuter(self, username="commuter"):
        user_id = create_account(
            username,
            f"{username}@example.com",
            "safe-password-123",
        )
        return user_id

    def test_three_failed_signins_lock_username(self):
        self.create_commuter()

        for _ in range(3):
            self.assertIsNone(authenticate("commuter", "incorrect-password"))

        self.assertGreater(login_lockout_seconds("commuter"), 0)
        self.assertIsNone(
            authenticate("commuter", "safe-password-123")
        )

    def test_schedule_search_returns_bus_route_times_and_fare(self):
        rows = fare_management.check_bus_schedule(
            "701",
            date.today().isoformat(),
        )

        self.assertTrue(rows)
        schedule = dict(rows[0])
        self.assertEqual(schedule["route_id"], "701")
        self.assertEqual(schedule["bus_number"], "JUTC-701-01")
        self.assertIn("departure_time", schedule)
        self.assertIn("arrival_time", schedule)
        self.assertGreater(schedule["fare_amount"], 0)

    def test_virtual_balance_limits_and_fare_deduction(self):
        user_id = self.create_commuter("wallet")
        fare_management.link_bus_card(user_id, "WALLET-CARD", 500)
        fare_management.top_up_main_balance(
            user_id,
            200,
            "Debit Card",
        )
        fare_management.update_virtual_balance(user_id, 300)
        moved_card = fare_management.get_linked_bus_card(user_id)
        self.assertEqual(float(moved_card["balance"]), 300.0)
        self.assertEqual(float(moved_card["main_balance"]), 400.0)

        with self.assertRaisesRegex(ValueError, "cannot be less"):
            fare_management.update_virtual_balance(user_id, 99)
        with self.assertRaisesRegex(ValueError, "main balance is too low"):
            fare_management.update_virtual_balance(user_id, 701)
        with self.assertRaisesRegex(ValueError, "at least JMD"):
            fare_management.pay_route_fare(user_id, "701")

        payment = fare_management.pay_route_fare(user_id, "702")
        updated_card = fare_management.get_linked_bus_card(user_id)

        self.assertEqual(payment["new_balance"], 120.0)
        self.assertEqual(float(updated_card["balance"]), 120.0)
        self.assertEqual(float(updated_card["main_balance"]), 400.0)
        self.assertEqual(len(fare_management.list_card_topups(user_id)), 1)

    def test_adding_to_virtual_balance_deducts_main_and_can_return(self):
        user_id = self.create_commuter("mover")
        fare_management.link_bus_card(user_id, "MOVER-CARD", 600)
        card = fare_management.get_linked_bus_card(user_id)
        self.assertEqual(float(card["balance"]), 100.0)
        self.assertEqual(float(card["main_balance"]), 500.0)

        fare_management.update_virtual_balance(user_id, 350)
        card = fare_management.get_linked_bus_card(user_id)
        self.assertEqual(float(card["balance"]), 350.0)
        self.assertEqual(float(card["main_balance"]), 250.0)

        fare_management.update_virtual_balance(user_id, 200)
        card = fare_management.get_linked_bus_card(user_id)
        self.assertEqual(float(card["balance"]), 200.0)
        self.assertEqual(float(card["main_balance"]), 400.0)

    def test_card_details_validation(self):
        ok = fare_management.validate_card_details(
            "A Person", "4111 1111 1111 1111", "12/99", "123"
        )
        self.assertEqual(ok, {"last4": "1111"})
        bad = [
            ("", "4111111111111111", "12/99", "123"),
            ("A", "4111111111111112", "12/99", "123"),
            ("A", "4111111111111111", "13/99", "123"),
            ("A", "4111111111111111", "01/20", "123"),
            ("A", "4111111111111111", "12/99", "12"),
        ]
        for args in bad:
            with self.assertRaises(ValueError):
                fare_management.validate_card_details(*args)

    def test_topup_records_only_last_four_digits(self):
        user_id = self.create_commuter("topper")
        fare_management.link_bus_card(user_id, "TOP-CARD", 100)
        result = fare_management.top_up_main_balance(
            user_id, 250, "Credit Card", card_last4="1111"
        )
        self.assertEqual(result["payment_method"], "Credit Card ending 1111")
        card = fare_management.get_linked_bus_card(user_id)
        self.assertEqual(float(card["main_balance"]), 250.0)


if __name__ == "__main__":
    unittest.main()

import unittest
from bus_system.bus_operations import validate_gps
from bus_system.fare_management import pay_fare
from bus_system.database import initialize_database

class TestCoreValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()

    def test_gps_valid_boundaries(self):
        self.assertEqual(validate_gps(90, -180, 0), (90.0, -180.0, 0.0))

    def test_gps_rejects_out_of_range_latitude(self):
        with self.assertRaises(ValueError):
            validate_gps(90.1, 0, 10)

    def test_gps_rejects_negative_speed(self):
        with self.assertRaises(ValueError):
            validate_gps(18, -77, -1)

    def test_cash_payment_exact_amount(self):
        result = pay_fare(300, "1", cash_amount=300)
        self.assertEqual(result["payment_status"], "Successful")
        self.assertEqual(result["change"], 0.0)

    def test_cash_payment_insufficient(self):
        with self.assertRaises(ValueError):
            pay_fare(300, "1", cash_amount=299)

    def test_invalid_payment_method(self):
        with self.assertRaises(ValueError):
            pay_fare(300, "3")

if __name__ == "__main__":
    unittest.main()

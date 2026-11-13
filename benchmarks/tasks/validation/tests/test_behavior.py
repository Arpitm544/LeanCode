import unittest
from ports import validate_port
class PortTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_port(443), 443)
    def test_invalid(self):
        for value in (0, 65536, True, '443'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_port(value)

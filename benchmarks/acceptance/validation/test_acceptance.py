import unittest
from ports import validate_port
class Acceptance(unittest.TestCase):
    def test_all_edges(self):
        for value in (1, 65535):
            self.assertEqual(validate_port(value), value)
        for value in (-1, False, 1.2, None, [], '1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_port(value)

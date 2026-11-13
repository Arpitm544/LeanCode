import unittest
from checkout import quote
from receipt import receipt_total
class CallerTests(unittest.TestCase):
    def test_forward_tax(self):
        self.assertEqual(quote(10, 2, tax_rate=0.1), 22)
        self.assertEqual(receipt_total(10, 2, tax_rate=0.1), 22)
    def test_old_callers(self):
        self.assertEqual(quote(10, 2), 20)

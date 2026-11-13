import unittest
from pricing import total
from checkout import quote
from receipt import receipt_total
class Acceptance(unittest.TestCase):
    def test_round_and_forward(self):
        for function in (total, quote, receipt_total):
            self.assertEqual(function(3.33, 3, tax_rate=0.07), 10.69)
            self.assertEqual(function(0, 3, tax_rate=0.2), 0)

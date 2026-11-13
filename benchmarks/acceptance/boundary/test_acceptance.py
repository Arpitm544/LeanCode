import unittest
from maths import is_positive
class Acceptance(unittest.TestCase):
    def test_fractional_edges(self):
        self.assertFalse(is_positive(0.0))
        self.assertFalse(is_positive(-0.001))
        self.assertTrue(is_positive(0.001))

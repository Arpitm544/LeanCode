import unittest
from maths import is_positive
class BoundaryTests(unittest.TestCase):
    def test_boundaries(self):
        self.assertFalse(is_positive(0))
        self.assertFalse(is_positive(-1))
        self.assertTrue(is_positive(1))

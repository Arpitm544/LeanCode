import unittest
from catalog import get_item
from cart import discounted
class CatalogTests(unittest.TestCase):
    def test_no_price_mutation(self):
        self.assertEqual(discounted('book')['price'], 10)
        self.assertEqual(get_item('book')['price'], 20)

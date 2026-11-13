import unittest
from catalog import get_item
class Acceptance(unittest.TestCase):
    def test_nested_isolation(self):
        item = get_item('book')
        item['metadata']['tags'].append('changed')
        self.assertEqual(get_item('book')['metadata']['tags'], ['new'])
        with self.assertRaises(KeyError):
            get_item('unknown')

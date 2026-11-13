import unittest
from formatters import article_path, tag_path
class FormatTests(unittest.TestCase):
    def test_behavior(self):
        self.assertEqual(article_path(' Hello World '), '/articles/hello-world')
        self.assertEqual(tag_path(' A  B '), '/tags/a--b')

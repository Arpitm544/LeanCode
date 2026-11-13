import ast
import inspect
import unittest
import formatters
class Acceptance(unittest.TestCase):
    def test_helper_and_callers(self):
        self.assertEqual(formatters.slug(' A  B '), 'a--b')
        for function in (formatters.article_path, formatters.tag_path):
            tree = ast.parse(inspect.getsource(function))
            self.assertTrue(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'slug' for n in ast.walk(tree)))

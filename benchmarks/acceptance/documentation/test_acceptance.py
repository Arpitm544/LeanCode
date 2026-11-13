import unittest
from run_tests import discovery_args
class Acceptance(unittest.TestCase):
    def test_default_and_spaces(self):
        self.assertEqual(discovery_args('my tests'), ['python', '-m', 'unittest', 'discover', '-s', 'my tests', '-p', 'test*.py'])

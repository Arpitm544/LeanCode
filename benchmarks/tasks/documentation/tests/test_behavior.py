import unittest
from run_tests import discovery_args
class DiscoveryTests(unittest.TestCase):
    def test_pattern(self):
        self.assertEqual(discovery_args('checks', 'check_*.py'), ['python', '-m', 'unittest', 'discover', '-s', 'checks', '-p', 'check_*.py'])

import unittest
import random
from test_coverage.agents.new_agent_01 import CalcDemo
from test_coverage import SkipUnitTest

@SkipUnitTest
class TestDemo(unittest.TestCase):

    def test_plus(self):
        self.assertEqual(CalcDemo(6, 4).plus(), 10)

    def test_subtract(self):
        self.assertEqual(CalcDemo(6, 4).subtract(), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)

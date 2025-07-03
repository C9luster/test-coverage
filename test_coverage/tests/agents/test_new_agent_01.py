import unittest
from test_coverage.agents.new_agent_01 import CalcDemo


class TestDemo(unittest.TestCase):

    def test_plus(self):
        self.assertEqual(CalcDemo(6, 4).plus(), 10)

    def test_subtract(self):
        self.assertEqual(CalcDemo(6, 4).subtract(), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)

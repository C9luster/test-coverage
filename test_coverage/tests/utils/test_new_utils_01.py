import unittest
import random
from test_coverage.utils.util import utilsDemo


class TestDemo(unittest.TestCase):

    def test_plus(self):
        self.assertEqual(utilsDemo(6, 4).plus(), 10)

    def test_subtract(self):
        self.assertEqual(utilsDemo(6, 4).subtract(), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)

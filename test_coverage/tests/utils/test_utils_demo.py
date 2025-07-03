import unittest
from test_coverage.utils.utils_demo import UtilsDemo

class TestUtilsDemo(unittest.TestCase):
    def test_multiply(self):
        self.assertEqual(UtilsDemo(2, 3).multiply(), 6)
        self.assertEqual(UtilsDemo(-1, 1).multiply(), 0)

    def test_divide(self):
        self.assertEqual(UtilsDemo(6, 3).divide(), 2)
        self.assertAlmostEqual(UtilsDemo(7, 2).divide(), 3.5)
        with self.assertRaises(ValueError):
            UtilsDemo(1, 0).divide()

if __name__ == "__main__":
    unittest.main() 
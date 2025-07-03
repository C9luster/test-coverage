import unittest
from test_coverage.agents.agent_demo import AgentDemo
import random
from test_coverage import SerialTest

@SerialTest
class TestAgentDemo(unittest.TestCase):
    def test_add(self):
        self.assertEqual(AgentDemo(2, 3).add(), 5)
        self.assertEqual(AgentDemo(-1, 1).add(), 0)

    def test_subtract(self):
        self.assertEqual(AgentDemo(5, 3).subtract(), 2)
        self.assertEqual(AgentDemo(0, 1).subtract(), -1)

if __name__ == "__main__":
    unittest.main() 
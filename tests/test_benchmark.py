from __future__ import annotations

import json
import unittest

from ai.agents import RandomAgent
from arena.selfplay import SelfPlayRunner
from benchmark.report import build_report


class BenchmarkTests(unittest.TestCase):
    def test_report_contains_real_side_swapped_metrics(self) -> None:
        result = SelfPlayRunner(RandomAgent(1), RandomAgent(2), max_turns=3).run((50,))
        report = build_report(result)
        payload = report.to_dict()

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["metadata"]["seeds"], [50])
        self.assertTrue(payload["metadata"]["side_swapped"])
        self.assertIn("win_rate", payload["metrics"])
        self.assertIn("latency_p95_ms", payload["metrics"])
        self.assertIn("search_nodes", payload["metrics"])
        self.assertEqual(json.loads(report.to_json()), payload)


if __name__ == "__main__":
    unittest.main()

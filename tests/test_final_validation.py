from __future__ import annotations

import unittest

from benchmark.final_validation import run_validation


class FinalValidationTests(unittest.TestCase):
    def test_smoke_report_has_each_completion_criterion_once(self) -> None:
        report = run_validation(mode="smoke", games=1, max_turns=1, duration_seconds=0.01)
        criteria = report.to_dict()["criteria"]

        self.assertEqual([item["id"] for item in criteria], list(range(1, 11)))
        self.assertEqual(len({item["id"] for item in criteria}), 10)
        self.assertFalse(report.ok)
        self.assertEqual(criteria[4]["status"], "fail")
        self.assertEqual(criteria[8]["status"], "fail")
        self.assertGreater(len(report.final_report_hash), 0)

    def test_report_is_machine_readable(self) -> None:
        report = run_validation(mode="smoke", games=1, max_turns=1, duration_seconds=0.01)
        payload = report.to_dict()

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["mode"], "smoke")
        self.assertIn("event_log_hash", payload)
        self.assertEqual(payload, report.to_json_dict())


if __name__ == "__main__":
    unittest.main()

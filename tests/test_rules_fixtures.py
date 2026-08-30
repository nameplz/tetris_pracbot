from __future__ import annotations

import json
from pathlib import Path
import unittest

from engine.rules import seven_bag
from engine.state import Ruleset


FIXTURE = Path(__file__).parent / "fixtures/ruleset_cases.json"


class RulesFixtureTests(unittest.TestCase):
    def test_ruleset_fixture_matches_version_and_seeded_bag(self) -> None:
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))

        self.assertEqual(Ruleset.default().version, data["ruleset_version"])
        self.assertEqual(10, data["visible_board"]["width"])
        self.assertEqual(20, data["visible_board"]["height"])
        actual = [piece.kind for piece in seven_bag(data["seven_bag"]["seed"], 14)]
        self.assertEqual(data["seven_bag"]["pieces"], actual)

    def test_ruleset_fixture_source_is_tracked_by_default_ruleset(self) -> None:
        self.assertIn("docs/completion-criteria.md", Ruleset.default().fixture_sources)


if __name__ == "__main__":
    unittest.main()

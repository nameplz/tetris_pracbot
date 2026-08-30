from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from ai.search import BeamSearchAgent
from engine.movegen import generate_candidates
from engine.rules import initial_game_state
from engine.state import stable_json


class SearchTests(unittest.TestCase):
    def test_search_is_bounded_deterministic_and_legal(self) -> None:
        state = initial_game_state(21)
        before = stable_json(state)
        agent = BeamSearchAgent(depth=2, beam_width=3, time_budget_ms=5000)

        first = agent.search(state)
        second = agent.search(state)

        self.assertEqual(first.root_move, second.root_move)
        self.assertGreater(first.nodes_searched, 0)
        self.assertGreaterEqual(first.completed_depth, 1)
        self.assertGreaterEqual(first.nodes_per_second, 0)
        self.assertIn(first.root_move.signature, {item.signature for item in generate_candidates(state)})
        self.assertEqual(before, stable_json(state))
        self.assertEqual(first.root_move, agent.choose_move(state))

    def test_budget_can_return_a_legal_fallback(self) -> None:
        state = initial_game_state(22)
        result = BeamSearchAgent(depth=3, beam_width=2, time_budget_ms=1).search(state)

        self.assertIn(result.root_move.signature, {item.signature for item in generate_candidates(state)})
        self.assertTrue(result.fallback_used or result.completed_depth >= 1)

    def test_search_configuration_is_validated_and_immutable(self) -> None:
        with self.assertRaises(ValueError):
            BeamSearchAgent(depth=0)
        with self.assertRaises(ValueError):
            BeamSearchAgent(beam_width=0)
        with self.assertRaises(ValueError):
            BeamSearchAgent(time_budget_ms=0)
        agent = BeamSearchAgent()
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            agent.depth = 4  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()

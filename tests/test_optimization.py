from __future__ import annotations

import unittest

from ai.search import BeamSearchAgent, OptimizedBeamSearchAgent
from benchmark.optimization import build_optimization_profile
from engine.movegen import generate_candidates
from engine.rules import initial_game_state


class OptimizationTests(unittest.TestCase):
    def test_optimized_search_keeps_legal_deterministic_output(self) -> None:
        state = initial_game_state(61)
        agent = OptimizedBeamSearchAgent(depth=2, beam_width=2, time_budget_ms=5000)

        first = agent.search(state)
        second = agent.search(state)

        self.assertEqual(first.root_move, second.root_move)
        self.assertGreaterEqual(first.cache_hits, 0)
        self.assertIn(first.root_move.signature, {item.signature for item in generate_candidates(state)})
        self.assertTrue(agent.cache_enabled)
        self.assertFalse(BeamSearchAgent().cache_enabled)

    def test_profile_uses_explicit_seed_and_side_swap_metadata(self) -> None:
        profile = build_optimization_profile(seed=62, samples=1, max_turns=1)

        self.assertEqual(profile["metadata"]["seed"], 62)
        self.assertTrue(profile["metadata"]["side_swapped"])
        self.assertIn("baseline", profile)
        self.assertIn("optimized", profile)


if __name__ == "__main__":
    unittest.main()

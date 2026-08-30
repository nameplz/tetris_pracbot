from __future__ import annotations

from dataclasses import replace
import unittest

from ai.agents import RandomAgent
from arena.selfplay import SelfPlayRunner
from arena.simulator import LocalSimulator
from engine.movegen import Move


class InvalidAgent:
    def choose_move(self, state, player_index=0) -> Move:
        from engine.movegen import generate_candidates

        move = generate_candidates(state, player_index)[0].move
        return replace(move, x=move.x + 100)


class SimulatorTests(unittest.TestCase):
    def test_match_is_headless_and_event_log_is_reproducible(self) -> None:
        first = LocalSimulator(31, (RandomAgent(1), RandomAgent(2)), max_turns=6).run()
        second = LocalSimulator(31, (RandomAgent(1), RandomAgent(2)), max_turns=6).run()

        self.assertGreater(len(first.events), 0)
        self.assertEqual(first.event_log, second.event_log)
        self.assertEqual(first.winner, second.winner)
        self.assertEqual(first.invalid_moves, 0)
        self.assertEqual(first.invalid_candidates, 0)
        self.assertEqual(first.events[0].seed, 31)

    def test_invalid_move_is_counted_and_other_side_wins(self) -> None:
        result = LocalSimulator(32, (InvalidAgent(), RandomAgent(2)), max_turns=4).run()

        self.assertEqual(result.invalid_moves, 1)
        self.assertEqual(result.winner, 1)
        self.assertTrue(result.terminal)

    def test_side_swapped_self_play_isolated_per_match(self) -> None:
        runner = SelfPlayRunner(RandomAgent(1), RandomAgent(2), max_turns=4)
        first = runner.run((40, 41))
        second = runner.run((40, 41))

        self.assertEqual(len(first.matches), 4)
        self.assertTrue(first.side_swapped)
        self.assertEqual(
            tuple(match.event_log for match in first.matches),
            tuple(match.event_log for match in second.matches),
        )


if __name__ == "__main__":
    unittest.main()

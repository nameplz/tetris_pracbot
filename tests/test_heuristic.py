from __future__ import annotations

from dataclasses import replace
import unittest

from ai.agents import GreedyAgent, RandomAgent
from ai.heuristic import FeatureVector, HeuristicEvaluator, WeightSet, extract_features
from engine.movegen import generate_candidates
from engine.rules import initial_game_state
from engine.state import Board, stable_json


def board_with_rows(rows: tuple[str, ...]) -> Board:
    empty = Board.empty()
    cells = [list(row) for row in empty.cells]
    for index, row in enumerate(rows, start=empty.buffer_height):
        cells[index] = list(row)
    return empty.with_cells(tuple(tuple(row) for row in cells))


class HeuristicTests(unittest.TestCase):
    def test_feature_vector_serializes_board_attack_and_context(self) -> None:
        state = initial_game_state(9)
        candidate = generate_candidates(state, 0)[0]
        features = extract_features(candidate, 0)

        self.assertEqual(
            set(features.to_dict()),
            {
                "holes",
                "covered_holes",
                "stack_height",
                "bumpiness",
                "wells",
                "top_out_risk",
                "lines_cleared",
                "attack",
                "cancel",
                "combo",
                "b2b",
                "surge",
                "all_clear",
                "clutch_clear",
                "incoming_garbage",
                "opponent_pressure",
            },
        )
        self.assertEqual(features, extract_features(candidate, 0))
        self.assertIsInstance(features.to_dict(), dict)

    def test_holes_and_height_are_measurable(self) -> None:
        state = initial_game_state(9)
        candidate = generate_candidates(state, 0)[0]
        board = board_with_rows(("X.........", "X.........", ".........."))
        altered_state = replace(
            candidate.state,
            players=(replace(candidate.state.players[0], board=board), candidate.state.players[1]),
        )
        altered = extract_features(replace(candidate, state=altered_state), 0)

        self.assertGreater(altered.stack_height, 0)
        self.assertGreaterEqual(altered.holes, 0)
        self.assertGreaterEqual(altered.covered_holes, 0)

    def test_score_ordering_respects_death_and_attack(self) -> None:
        evaluator = HeuristicEvaluator()
        safe = FeatureVector(attack=2)
        dangerous = FeatureVector(top_out_risk=1, attack=20)

        self.assertGreater(evaluator.evaluate_features(safe), evaluator.evaluate_features(dangerous))
        self.assertGreater(
            evaluator.evaluate_features(FeatureVector(attack=2)),
            evaluator.evaluate_features(FeatureVector()),
        )

    def test_agents_return_legal_moves_without_mutating_state(self) -> None:
        state = initial_game_state(12)
        before = stable_json(state)
        candidates = generate_candidates(state, 0)
        greedy_move = GreedyAgent().choose_move(state)
        random_move = RandomAgent(seed=4).choose_move(state)

        self.assertEqual(before, stable_json(state))
        self.assertIn(greedy_move.signature, {candidate.signature for candidate in candidates})
        self.assertIn(random_move.signature, {candidate.signature for candidate in candidates})

    def test_seeded_random_is_reproducible(self) -> None:
        state = initial_game_state(12)
        first = RandomAgent(seed=4).choose_move(state)
        second = RandomAgent(seed=4).choose_move(state)
        self.assertEqual(first, second)

    def test_weight_set_is_immutable(self) -> None:
        weights = WeightSet.bot_standard()
        with self.assertRaises((AttributeError, TypeError)):
            weights.holes = 0  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import replace
import unittest

from engine.movegen import (
    Candidate,
    Move,
    generate_candidates,
    replay_path,
    validate_move,
)
from engine.rules import initial_game_state


class MoveGeneratorTests(unittest.TestCase):
    def test_candidates_are_reachable_and_deduplicated(self) -> None:
        state = initial_game_state(5)

        candidates = generate_candidates(state, 0)

        self.assertGreater(len(candidates), 0)
        signatures = [candidate.move.signature for candidate in candidates]
        self.assertEqual(len(signatures), len(set(signatures)))
        for candidate in candidates:
            branch_state = state
            if candidate.move.use_hold:
                branch_state = replace(
                    state,
                    players=(
                        replace(state.players[0], hold_piece=state.players[0].current_piece),
                        state.players[1],
                    ),
                )
                branch_state = replace(
                    branch_state,
                    players=(
                        replace(
                            branch_state.players[0],
                            current_piece=branch_state.players[0].hold_piece,
                        ),
                        branch_state.players[1],
                    ),
                )
            replayed = replay_path(
                branch_state.players[0].board,
                candidate.move.piece if candidate.move.use_hold else state.players[0].current_piece,
                candidate.move.input_path,
            )
            self.assertEqual(candidate.move.x, replayed.x)
            self.assertEqual(candidate.move.y, replayed.y)
            self.assertEqual(candidate.move.rotation, replayed.piece.rotation)

    def test_candidates_have_stable_order_and_include_hold(self) -> None:
        state = initial_game_state(5)

        first = generate_candidates(state, 0)
        second = generate_candidates(state, 0)

        self.assertEqual(first, second)
        self.assertTrue(any(candidate.move.use_hold for candidate in first))

    def test_hold_candidate_uses_held_piece_and_validates_against_state(self) -> None:
        state = initial_game_state(5)
        held_state = replace(state, players=(replace(state.players[0], hold_piece=state.players[0].current_piece), state.players[1]))

        candidates = generate_candidates(held_state, 0)
        hold_candidate = next(candidate for candidate in candidates if candidate.move.use_hold)

        self.assertEqual(held_state.players[0].hold_piece.kind, hold_candidate.move.piece.kind)
        self.assertEqual(hold_candidate, validate_move(held_state, 0, hold_candidate.move))

    def test_invalid_move_is_rejected(self) -> None:
        state = initial_game_state(5)
        candidate = generate_candidates(state, 0)[0]
        invalid = replace(candidate.move, x=candidate.move.x + 20)

        with self.assertRaises(ValueError):
            validate_move(state, 0, invalid)

    def test_move_values_are_immutable(self) -> None:
        state = initial_game_state(5)
        move = generate_candidates(state, 0)[0].move

        self.assertIsInstance(move.input_path, tuple)
        with self.assertRaises((AttributeError, TypeError)):
            move.x = 0  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()

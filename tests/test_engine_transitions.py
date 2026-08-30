from __future__ import annotations

import unittest

from engine.rules import (
    classify_t_spin,
    hard_drop,
    hold_current_piece,
    initial_game_state,
    lock_piece,
    piece_cells,
    rotate_placement,
    seven_bag,
)
from engine.state import Board, GameState, Piece, PlayerState, Ruleset


class EngineTransitionTests(unittest.TestCase):
    def test_seven_bag_is_seeded_and_each_bag_contains_each_piece_once(self) -> None:
        first = seven_bag(seed=12, count=14)
        second = seven_bag(seed=12, count=14)

        self.assertEqual(first, second)
        self.assertEqual(14, len(first))
        self.assertEqual({"I", "J", "L", "O", "S", "T", "Z"}, {p.kind for p in first[:7]})
        self.assertEqual({"I", "J", "L", "O", "S", "T", "Z"}, {p.kind for p in first[7:]})

    def test_initial_game_state_has_same_seeded_queue_for_both_sides(self) -> None:
        state = initial_game_state(99)

        self.assertEqual(state.players[0].current_piece, state.players[1].current_piece)
        self.assertEqual(state.players[0].next_queue, state.players[1].next_queue)
        self.assertEqual(5, len(state.players[0].next_queue))

    def test_hold_swaps_once_and_resets_only_after_lock(self) -> None:
        state = initial_game_state(99)
        current = state.players[0].current_piece

        held = hold_current_piece(state, 0)

        self.assertEqual(current.kind, held.players[0].hold_piece.kind)
        self.assertTrue(held.players[0].hold_used)
        with self.assertRaises(ValueError):
            hold_current_piece(held, 0)

    def test_hard_drop_and_rotation_return_legal_placements(self) -> None:
        board = Board.empty()
        placement = hard_drop(board, Piece("T"), x=3)
        rotated = rotate_placement(board, placement, clockwise=True)

        self.assertEqual(22, placement.y)
        self.assertIsNotNone(rotated)
        self.assertTrue(all(board.cell(y, x) == "." for x, y in piece_cells(rotated)))

    def test_lock_clears_full_rows_and_advances_queue(self) -> None:
        rows = [list(row) for row in Board.empty().cells]
        rows[-1] = list("XXX....XXX")
        player = PlayerState(
            board=Board(cells=tuple(tuple(row) for row in rows)),
            current_piece=Piece("I"),
            next_queue=(Piece("T"), Piece("O")),
        )
        state = GameState(seed=1, ruleset=Ruleset.default(), players=(player, player))

        result = lock_piece(state, 0, hard_drop(player.board, player.current_piece, x=3))

        self.assertEqual(1, result.lines_cleared)
        self.assertEqual("T", result.state.players[0].current_piece.kind)
        self.assertFalse(result.state.players[0].hold_used)
        self.assertEqual(20, len(result.state.players[0].board.visible_rows))

    def test_t_spin_requires_rotated_t_and_three_occupied_corners(self) -> None:
        rows = [list(row) for row in Board.empty().cells]
        rows[10][3] = "X"
        rows[10][5] = "X"
        rows[12][3] = "X"
        board = Board(cells=tuple(tuple(row) for row in rows))

        self.assertEqual("full", classify_t_spin(board, Piece("T", 1), x=3, y=10, rotated=True))
        self.assertEqual("none", classify_t_spin(board, Piece("I", 1), x=3, y=10, rotated=True))


if __name__ == "__main__":
    unittest.main()

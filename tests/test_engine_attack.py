from __future__ import annotations

import unittest

from engine.attack import (
    apply_due_garbage,
    calculate_attack,
    enqueue_garbage,
    resolve_attack,
)
from engine.rules import initial_game_state


class EngineAttackTests(unittest.TestCase):
    def test_attack_includes_line_clear_spin_combo_and_all_clear(self) -> None:
        outcome = calculate_attack(
            lines_cleared=4,
            spin_kind="full",
            combo=3,
            b2b_charging=True,
            all_clear=True,
            surge=2,
        )

        self.assertGreater(outcome.total_attack, 4)
        self.assertTrue(outcome.b2b_bonus > 0)
        self.assertTrue(outcome.all_clear_bonus > 0)

    def test_attack_cancels_incoming_before_sending_remaining_lines(self) -> None:
        state = initial_game_state(8)
        state = enqueue_garbage(state, 0, lines=2, arrival_tick=1, hole=4)
        outcome = calculate_attack(lines_cleared=4)

        result = resolve_attack(state, 0, outcome)

        self.assertEqual(2, result.cancelled)
        self.assertEqual(2, result.sent)
        self.assertEqual(0, len(result.state.players[0].garbage_queue))
        self.assertEqual(1, len(result.state.players[1].garbage_queue))
        self.assertEqual(2, result.state.players[1].garbage_queue[0].lines)

    def test_due_garbage_changes_board_and_is_deterministic(self) -> None:
        state = initial_game_state(21)
        queued = enqueue_garbage(state, 0, lines=1, arrival_tick=0, hole=3)

        applied = apply_due_garbage(queued, 0)

        self.assertEqual(0, len(applied.players[0].garbage_queue))
        self.assertEqual(".", applied.players[0].board.cells[-1][3])
        self.assertEqual("X", applied.players[0].board.cells[-1][2])
        self.assertEqual(applied, apply_due_garbage(queued, 0))

    def test_attack_rejects_invalid_line_count(self) -> None:
        with self.assertRaises(ValueError):
            calculate_attack(lines_cleared=5)


if __name__ == "__main__":
    unittest.main()

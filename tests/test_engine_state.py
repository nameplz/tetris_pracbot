from __future__ import annotations

import json
import unittest

from engine.state import (
    Board,
    BotStandardPreset,
    GarbagePacket,
    GameState,
    Piece,
    PlayerState,
    Ruleset,
    StreakState,
    stable_json,
)


class EngineStateTests(unittest.TestCase):
    def test_bot_standard_preset_matches_documented_defaults(self) -> None:
        preset = BotStandardPreset.default()

        self.assertEqual("bot_standard", preset.name)
        self.assertEqual(10, preset.visible_width)
        self.assertEqual(20, preset.visible_height)
        self.assertEqual(5, preset.next_size)
        self.assertEqual(7, preset.bag_size)
        self.assertTrue(preset.hold_enabled)
        self.assertTrue(preset.hard_drop_enabled)
        self.assertEqual(0.0, preset.gravity)
        self.assertEqual(500, preset.lock_delay_ms)

    def test_ruleset_rejects_non_deterministic_or_unsupported_configuration(self) -> None:
        with self.assertRaises(ValueError):
            Ruleset(visible_width=9)
        with self.assertRaises(ValueError):
            Ruleset(bag_size=6)
        with self.assertRaises(ValueError):
            Ruleset(gravity=1.0)
        with self.assertRaises(ValueError):
            Ruleset(lock_delay_ms=0)

    def test_game_state_is_immutable_and_has_stable_json(self) -> None:
        ruleset = Ruleset.default()
        player = PlayerState.empty()
        state = GameState(seed=42, ruleset=ruleset, players=(player, player))

        with self.assertRaises((AttributeError, TypeError)):
            state.seed = 43  # type: ignore[misc]

        encoded = stable_json(state)
        self.assertEqual(encoded, stable_json(state))
        decoded = json.loads(encoded)
        self.assertEqual(42, decoded["seed"])
        self.assertEqual("tetrio-public-2026-08-30", decoded["ruleset"]["version"])

    def test_nested_state_uses_values_not_mutable_inputs(self) -> None:
        source_rows = tuple(tuple("." for _ in range(10)) for _ in range(24))
        board = Board(cells=source_rows)
        queue = (Piece("T"), Piece("I"))
        player = PlayerState(board=board, next_queue=queue)
        state = GameState(seed=7, ruleset=Ruleset.default(), players=(player, player))

        self.assertIsInstance(state.players, tuple)
        self.assertIsInstance(state.players[0].next_queue, tuple)
        self.assertEqual("T", state.players[0].next_queue[0].kind)

    def test_boundary_values_are_validated(self) -> None:
        with self.assertRaises(ValueError):
            Piece("Q")
        with self.assertRaises(ValueError):
            Board(cells=(tuple("." for _ in range(9)),) * 24)
        with self.assertRaises(ValueError):
            GarbagePacket(lines=0, hole=0, arrival_tick=0)
        with self.assertRaises(ValueError):
            StreakState(combo=-2)


if __name__ == "__main__":
    unittest.main()

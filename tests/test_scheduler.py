from __future__ import annotations

import unittest

from ai.agents import RandomAgent
from arena.simulator import LocalSimulator
from engine.movegen import generate_candidates
from engine.rules import initial_game_state
from visual.replay import ReplayController
from visual.scheduler import ExecutionScheduler


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class SchedulerTests(unittest.TestCase):
    def test_scheduler_is_paused_by_default_and_does_not_change_move(self) -> None:
        clock = FakeClock()
        move = generate_candidates(initial_game_state(70))[0].move
        scheduler = ExecutionScheduler(target_pps=0.6, clock=clock)
        scheduler.enqueue(move)

        self.assertTrue(scheduler.snapshot.paused)
        event = scheduler.step()
        self.assertIsNotNone(event)
        self.assertIs(event.move, move)
        self.assertEqual(scheduler.snapshot.emitted, 1)
        self.assertEqual(scheduler.snapshot.target_pps, 0.6)

    def test_start_pause_resume_and_overdue_policy(self) -> None:
        clock = FakeClock()
        move = generate_candidates(initial_game_state(71))[0].move
        scheduler = ExecutionScheduler(target_pps=1.0, clock=clock)
        scheduler.enqueue(move)
        scheduler.enqueue(move)
        scheduler.start()
        self.assertEqual(len(scheduler.poll()), 1)
        scheduler.pause()
        clock.value = 5.0
        self.assertEqual(scheduler.poll(), ())
        scheduler.resume()
        self.assertEqual(scheduler.snapshot.next_due, 5.0)
        self.assertGreaterEqual(scheduler.snapshot.timing_error, -1.0)

    def test_pps_is_validated(self) -> None:
        with self.assertRaises(ValueError):
            ExecutionScheduler(target_pps=0.5)


class ReplayTests(unittest.TestCase):
    def test_replay_starts_paused_and_supports_step_replay_quit(self) -> None:
        result = LocalSimulator(72, (RandomAgent(1), RandomAgent(2)), max_turns=2).run()
        replay = ReplayController(result.events, speed_pps=0.6)

        self.assertTrue(replay.snapshot.paused)
        event = replay.step()
        self.assertIsNotNone(event)
        self.assertEqual(replay.snapshot.tick, event.tick)
        replay.replay()
        self.assertEqual(replay.snapshot.position, 0)
        replay.quit()
        self.assertTrue(replay.snapshot.quit)
        self.assertIsNone(replay.step())


if __name__ == "__main__":
    unittest.main()

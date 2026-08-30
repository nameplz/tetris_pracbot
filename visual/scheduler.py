"""Monotonic-clock Move timing without changing the selected Move."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Callable

from engine.movegen import Move


MIN_PPS = 0.6


def _validate_pps(value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError("target PPS must be a finite number")
    if value < MIN_PPS:
        raise ValueError(f"target PPS must be >= {MIN_PPS}")
    return float(value)


@dataclass(frozen=True, slots=True)
class ScheduledMove:
    sequence: int
    move: Move
    due_at: float
    emitted_at: float

    @property
    def lateness(self) -> float:
        return max(0.0, self.emitted_at - self.due_at)


@dataclass(frozen=True, slots=True)
class ScheduleSnapshot:
    target_pps: float
    actual_pps: float
    timing_error: float
    next_due: float | None
    emitted: int
    queued: int
    started: bool
    paused: bool
    quit: bool


class ExecutionScheduler:
    def __init__(self, target_pps: float = MIN_PPS, *, clock: Callable[[], float] | None = None) -> None:
        self._target_pps = _validate_pps(target_pps)
        self._clock = clock or time.monotonic
        self._queue: tuple[Move, ...] = ()
        self._started = False
        self._paused = True
        self._quit = False
        self._started_at: float | None = None
        self._next_due: float | None = None
        self._emitted = 0

    @property
    def interval(self) -> float:
        return 1.0 / self._target_pps

    @property
    def snapshot(self) -> ScheduleSnapshot:
        now = self._clock()
        elapsed = 0.0 if self._started_at is None else max(0.0, now - self._started_at)
        actual = 0.0 if not self._emitted else self._emitted / max(elapsed, self.interval)
        return ScheduleSnapshot(
            target_pps=self._target_pps,
            actual_pps=actual,
            timing_error=(actual - self._target_pps) / self._target_pps,
            next_due=self._next_due,
            emitted=self._emitted,
            queued=len(self._queue),
            started=self._started,
            paused=self._paused,
            quit=self._quit,
        )

    def enqueue(self, move: Move) -> None:
        if not isinstance(move, Move):
            raise ValueError("scheduler accepts only Move")
        if self._quit:
            raise ValueError("scheduler has quit")
        self._queue = self._queue + (move,)
        if self._started and self._next_due is None:
            self._next_due = self._clock()

    def set_target_pps(self, target_pps: float) -> None:
        self._target_pps = _validate_pps(target_pps)
        if self._started and not self._paused and self._queue:
            self._next_due = self._clock() + self.interval

    def start(self) -> None:
        if self._quit:
            raise ValueError("scheduler has quit")
        if not self._started:
            self._started_at = self._clock()
        self._started = True
        self._paused = False
        if self._queue and self._next_due is None:
            self._next_due = self._clock()

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        if self._quit:
            raise ValueError("scheduler has quit")
        if not self._started:
            self.start()
            return
        self._paused = False
        if self._queue:
            self._next_due = self._clock()

    def _emit(self, now: float, due_at: float) -> ScheduledMove:
        move = self._queue[0]
        self._queue = self._queue[1:]
        event = ScheduledMove(self._emitted, move, due_at, now)
        self._emitted += 1
        self._next_due = now + self.interval if self._queue else None
        return event

    def step(self) -> ScheduledMove | None:
        if self._quit or not self._queue:
            return None
        now = self._clock()
        if not self._started:
            self._started = True
            self._started_at = now
        return self._emit(now, self._next_due if self._next_due is not None else now)

    def poll(self) -> tuple[ScheduledMove, ...]:
        if self._quit or self._paused or not self._started or not self._queue:
            return ()
        now = self._clock()
        if self._next_due is None or now < self._next_due:
            return ()
        return (self._emit(now, self._next_due),)

    def quit(self) -> None:
        self._quit = True
        self._paused = True

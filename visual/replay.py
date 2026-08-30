"""Paused-by-default event replay controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from arena.simulator import Event
from engine.movegen import Move

from .scheduler import MIN_PPS, _validate_pps


@dataclass(frozen=True, slots=True)
class ReplaySnapshot:
    seed: int | None
    ruleset_version: str | None
    preset: str | None
    tick: int
    current_move: Move | None
    metrics: tuple[tuple[str, int | float], ...]
    position: int
    total: int
    speed_pps: float
    paused: bool
    quit: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "ruleset_version": self.ruleset_version,
            "preset": self.preset,
            "tick": self.tick,
            "current_move": self.current_move.to_dict() if self.current_move else None,
            "metrics": {name: value for name, value in self.metrics},
            "position": self.position,
            "total": self.total,
            "speed_pps": self.speed_pps,
            "paused": self.paused,
            "quit": self.quit,
        }


class ReplayController:
    def __init__(self, events: tuple[Event, ...], *, speed_pps: float = MIN_PPS) -> None:
        selected_events = tuple(events)
        if not all(isinstance(event, Event) for event in selected_events):
            raise ValueError("replay events must contain Event values")
        self._events = selected_events
        self._speed_pps = _validate_pps(speed_pps)
        self._position = 0
        self._paused = True
        self._quit = False

    @property
    def snapshot(self) -> ReplaySnapshot:
        event_index = min(max(self._position - 1, 0), len(self._events) - 1)
        event = self._events[event_index] if self._events else None
        return ReplaySnapshot(
            seed=event.seed if event else None,
            ruleset_version=event.ruleset_version if event else None,
            preset=event.preset if event else None,
            tick=event.tick if event else 0,
            current_move=event.move if event else None,
            metrics=(
                ("attack", event.attack),
                ("cancelled", event.cancelled),
                ("sent", event.sent),
                ("b2b", event.b2b),
                ("stack_height", event.stack_height),
            )
            if event
            else (),
            position=self._position,
            total=len(self._events),
            speed_pps=self._speed_pps,
            paused=self._paused,
            quit=self._quit,
        )

    def set_speed(self, speed_pps: float) -> None:
        self._speed_pps = _validate_pps(speed_pps)

    def start(self) -> None:
        if self._quit:
            raise ValueError("replay has quit")
        self._paused = False

    def pause(self) -> None:
        self._paused = True

    def _advance(self) -> Event | None:
        if self._quit or self._position >= len(self._events):
            return None
        event = self._events[self._position]
        self._position += 1
        return event

    def step(self) -> Event | None:
        if self._quit:
            return None
        return self._advance()

    def poll(self) -> Event | None:
        if self._paused:
            return None
        return self._advance()

    def replay(self) -> None:
        self._position = 0
        self._paused = True
        self._quit = False

    def quit(self) -> None:
        self._quit = True
        self._paused = True

"""Agents that select Moves without owning or mutating simulator state."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Protocol

from engine.movegen import Move, generate_candidates
from engine.state import GameState, stable_json

from .heuristic import HeuristicEvaluator


class Agent(Protocol):
    def choose_move(self, state: GameState, player_index: int = 0) -> Move:
        ...


@dataclass(frozen=True, slots=True)
class GreedyAgent:
    evaluator: HeuristicEvaluator = field(default_factory=HeuristicEvaluator)

    def choose_move(self, state: GameState, player_index: int = 0) -> Move:
        candidates = generate_candidates(state, player_index)
        if not candidates:
            raise ValueError("no legal Move candidates")
        scored = tuple((self.evaluator.evaluate(candidate, player_index).score, candidate) for candidate in candidates)
        best_score = max(score for score, _ in scored)
        return next(candidate.move for score, candidate in scored if score == best_score)


@dataclass(frozen=True, slots=True)
class RandomAgent:
    seed: int = 0

    def choose_move(self, state: GameState, player_index: int = 0) -> Move:
        candidates = generate_candidates(state, player_index)
        if not candidates:
            raise ValueError("no legal Move candidates")
        digest = hashlib.sha256(f"{self.seed}:{stable_json(state)}".encode("utf-8")).digest()
        index = int.from_bytes(digest[:8], "big") % len(candidates)
        return candidates[index].move

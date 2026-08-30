"""Bounded deterministic beam search over Candidate states."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

from engine.movegen import Candidate, Move, generate_candidates
from engine.state import GameState, stable_json

from .heuristic import HeuristicEvaluator


def _positive_int(name: str, value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class SearchResult:
    root_move: Move
    leaf_score: float
    nodes_searched: int
    nodes_per_second: float
    completed_depth: int
    elapsed_ms: float
    fallback_used: bool = False
    cache_hits: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_move": self.root_move.to_dict(),
            "leaf_score": self.leaf_score,
            "nodes_searched": self.nodes_searched,
            "nodes_per_second": self.nodes_per_second,
            "completed_depth": self.completed_depth,
            "elapsed_ms": self.elapsed_ms,
            "fallback_used": self.fallback_used,
            "cache_hits": self.cache_hits,
        }


@dataclass(frozen=True, slots=True)
class BeamSearchAgent:
    depth: int = 2
    beam_width: int = 10
    time_budget_ms: int = 100
    cache_enabled: bool = False
    evaluator: HeuristicEvaluator = field(default_factory=HeuristicEvaluator)

    def __post_init__(self) -> None:
        _positive_int("depth", self.depth)
        _positive_int("beam width", self.beam_width)
        _positive_int("time budget", self.time_budget_ms)
        if not isinstance(self.cache_enabled, bool):
            raise ValueError("cache_enabled must be a boolean")
        if not isinstance(self.evaluator, HeuristicEvaluator):
            raise ValueError("evaluator must be a HeuristicEvaluator")

    @staticmethod
    def _rank(scored: tuple[tuple[float, Candidate], ...]) -> tuple[tuple[float, Candidate], ...]:
        return tuple(
            sorted(
                scored,
                key=lambda item: (-item[0], item[1].move.signature, item[1].move.input_path),
            )
        )

    def choose_move(self, state: GameState, player_index: int = 0) -> Move:
        return self.search(state, player_index).root_move

    def search(self, state: GameState, player_index: int = 0) -> SearchResult:
        started = time.perf_counter()
        deadline = started + self.time_budget_ms / 1000.0
        candidate_cache: dict[tuple[str, int, int, int, int], tuple[Candidate, ...]] = {}
        cache_hits = 0

        def candidates_for(snapshot: GameState) -> tuple[Candidate, ...]:
            nonlocal cache_hits
            if not self.cache_enabled:
                return generate_candidates(snapshot, player_index)
            key = (
                stable_json(snapshot),
                player_index,
                self.depth,
                self.beam_width,
                self.time_budget_ms,
            )
            if key in candidate_cache:
                cache_hits += 1
                return candidate_cache[key]
            generated = generate_candidates(snapshot, player_index)
            candidate_cache[key] = generated
            return generated

        roots = candidates_for(state)
        if not roots:
            raise ValueError("no legal Move candidates")

        root_scored = self._rank(
            tuple((self.evaluator.evaluate(candidate, player_index).score, candidate) for candidate in roots)
        )
        best_score, best_candidate = root_scored[0]
        nodes = len(roots)
        completed_depth = 1
        frontier = tuple((candidate, candidate) for _, candidate in root_scored[: self.beam_width])
        timed_out = time.perf_counter() >= deadline

        for target_depth in range(2, self.depth + 1):
            if timed_out:
                break
            expanded: list[tuple[Candidate, Candidate]] = []
            layer_complete = True
            for root, leaf in frontier:
                if time.perf_counter() >= deadline:
                    layer_complete = False
                    break
                if leaf.state.players[player_index].top_out:
                    continue
                children = candidates_for(leaf.state)
                nodes += len(children)
                expanded.extend((root, child) for child in children)
                if time.perf_counter() >= deadline:
                    layer_complete = False
                    break
            if not layer_complete or not expanded:
                timed_out = timed_out or not layer_complete
                break
            ranked = tuple(
                sorted(
                    [
                        (self.evaluator.evaluate(leaf, player_index).score, root, leaf)
                        for root, leaf in expanded
                    ],
                    key=lambda item: (
                    -item[0],
                    item[1].move.signature,
                    item[2].move.signature,
                    item[2].move.input_path,
                ))
            )
            frontier = tuple((root, leaf) for _, root, leaf in ranked[: self.beam_width])
            best_score, best_candidate, _ = ranked[0]
            completed_depth = target_depth
            timed_out = time.perf_counter() >= deadline

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return SearchResult(
            root_move=best_candidate.move,
            leaf_score=best_score,
            nodes_searched=nodes,
            nodes_per_second=nodes / max(elapsed_ms / 1000.0, 1e-9),
            completed_depth=completed_depth,
            elapsed_ms=elapsed_ms,
            fallback_used=False,
            cache_hits=cache_hits,
        )


@dataclass(frozen=True, slots=True)
class OptimizedBeamSearchAgent(BeamSearchAgent):
    """Beam search with a per-decision immutable-state candidate cache."""

    cache_enabled: bool = True

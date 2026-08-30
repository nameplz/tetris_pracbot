"""Seeded, side-swapped self-play runner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.state import BotStandardPreset, Ruleset

from .simulator import AgentLike, LocalSimulator, MatchResult


@dataclass(frozen=True, slots=True)
class SelfPlayResult:
    agent_a: str
    agent_b: str
    seeds: tuple[int, ...]
    max_turns: int
    preset: str
    side_swapped: bool
    matches: tuple[MatchResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_a": self.agent_a,
            "agent_b": self.agent_b,
            "seeds": list(self.seeds),
            "max_turns": self.max_turns,
            "preset": self.preset,
            "side_swapped": self.side_swapped,
            "matches": [match.to_dict() for match in self.matches],
        }


class SelfPlayRunner:
    def __init__(
        self,
        agent_a: AgentLike,
        agent_b: AgentLike,
        *,
        ruleset: Ruleset | None = None,
        preset: BotStandardPreset | None = None,
        max_turns: int = 100,
    ) -> None:
        self.agent_a = agent_a
        self.agent_b = agent_b
        self.ruleset = ruleset
        self.preset = preset
        if not isinstance(max_turns, int) or isinstance(max_turns, bool) or max_turns <= 0:
            raise ValueError("max turns must be a positive integer")
        self.max_turns = max_turns

    @property
    def agent_names(self) -> tuple[str, str]:
        return type(self.agent_a).__name__, type(self.agent_b).__name__

    def run(self, seeds: tuple[int, ...]) -> SelfPlayResult:
        selected_seeds = tuple(seeds)
        if not selected_seeds or not all(isinstance(seed, int) and not isinstance(seed, bool) for seed in selected_seeds):
            raise ValueError("seeds must contain at least one integer")
        matches: list[MatchResult] = []
        for seed in selected_seeds:
            matches.append(
                LocalSimulator(
                    seed,
                    (self.agent_a, self.agent_b),
                    ruleset=self.ruleset,
                    preset=self.preset,
                    max_turns=self.max_turns,
                ).run()
            )
            matches.append(
                LocalSimulator(
                    seed,
                    (self.agent_b, self.agent_a),
                    ruleset=self.ruleset,
                    preset=self.preset,
                    max_turns=self.max_turns,
                ).run()
            )
        return SelfPlayResult(
            agent_a=self.agent_names[0],
            agent_b=self.agent_names[1],
            seeds=selected_seeds,
            max_turns=self.max_turns,
            preset=(self.preset or BotStandardPreset.default()).name,
            side_swapped=True,
            matches=tuple(matches),
        )

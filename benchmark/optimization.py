"""Small fixed-profile search measurements."""

from __future__ import annotations

from dataclasses import dataclass
import resource
import time
from typing import Any

from ai.search import BeamSearchAgent, OptimizedBeamSearchAgent
from engine.rules import initial_game_state
from engine.state import BotStandardPreset, stable_json

from .report import _percentile


@dataclass(frozen=True, slots=True)
class OptimizationMeasurement:
    agent: str
    seed: int
    preset: str
    samples: int
    latencies_ms: tuple[float, ...]
    search_nodes: tuple[int, ...]
    search_nodes_per_second: tuple[float, ...]
    move_signatures: tuple[tuple[object, ...], ...]
    max_rss_kb: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "seed": self.seed,
            "preset": self.preset,
            "samples": self.samples,
            "latency_p50_ms": _percentile(self.latencies_ms, 50),
            "latency_p95_ms": _percentile(self.latencies_ms, 95),
            "latency_p99_ms": _percentile(self.latencies_ms, 99),
            "search_nodes": sum(self.search_nodes) / max(len(self.search_nodes), 1),
            "search_nodes_per_second": sum(self.search_nodes_per_second)
            / max(len(self.search_nodes_per_second), 1),
            "move_signatures": [list(signature) for signature in self.move_signatures],
            "max_rss_kb": self.max_rss_kb,
        }


def measure_agent(
    agent: BeamSearchAgent,
    *,
    seed: int,
    samples: int,
    preset: BotStandardPreset,
) -> OptimizationMeasurement:
    if not isinstance(samples, int) or isinstance(samples, bool) or samples <= 0:
        raise ValueError("samples must be a positive integer")
    latencies: list[float] = []
    nodes: list[int] = []
    rates: list[float] = []
    signatures: list[tuple[object, ...]] = []
    for sample in range(samples):
        state = initial_game_state(seed + sample)
        for player_index in (0, 1):
            started = time.perf_counter()
            result = agent.search(state, player_index)
            latencies.append((time.perf_counter() - started) * 1000.0)
            nodes.append(result.nodes_searched)
            rates.append(result.nodes_per_second)
            signatures.append(result.root_move.signature)
    return OptimizationMeasurement(
        agent=type(agent).__name__,
        seed=seed,
        preset=preset.name,
        samples=samples,
        latencies_ms=tuple(latencies),
        search_nodes=tuple(nodes),
        search_nodes_per_second=tuple(rates),
        move_signatures=tuple(signatures),
        max_rss_kb=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
    )


def build_optimization_profile(
    *,
    seed: int,
    samples: int = 1,
    max_turns: int = 1,
    depth: int = 2,
    beam_width: int = 2,
    time_budget_ms: int = 500,
) -> dict[str, Any]:
    if not isinstance(max_turns, int) or isinstance(max_turns, bool) or max_turns <= 0:
        raise ValueError("max turns must be a positive integer")
    preset = BotStandardPreset.default()
    baseline = BeamSearchAgent(
        depth=depth,
        beam_width=beam_width,
        time_budget_ms=time_budget_ms,
        cache_enabled=False,
    )
    optimized = OptimizedBeamSearchAgent(
        depth=depth,
        beam_width=beam_width,
        time_budget_ms=time_budget_ms,
    )
    return {
        "schema_version": 1,
        "metadata": {
            "seed": seed,
            "samples": samples,
            "max_turns": max_turns,
            "preset": preset.name,
            "side_swapped": True,
            "depth": depth,
            "beam_width": beam_width,
            "time_budget_ms": time_budget_ms,
        },
        "baseline": measure_agent(baseline, seed=seed, samples=samples, preset=preset).to_dict(),
        "optimized": measure_agent(optimized, seed=seed, samples=samples, preset=preset).to_dict(),
    }

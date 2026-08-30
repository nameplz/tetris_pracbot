"""Stable aggregation of self-play match evidence."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Iterable

from arena.selfplay import SelfPlayResult


def _percentile(values: Iterable[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, int((percentile / 100.0) * len(ordered)))
    return float(ordered[index])


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    schema_version: int
    metadata: dict[str, Any]
    metrics: dict[str, float | int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "metadata": dict(self.metadata),
            "metrics": dict(self.metrics),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_report(result: SelfPlayResult) -> BenchmarkReport:
    if not isinstance(result, SelfPlayResult):
        raise ValueError("result must be a SelfPlayResult")
    wins = 0
    pieces = attacks = sent = cancelled = clears = top_outs = 0
    b2b_values: list[float] = []
    stack_values: list[float] = []
    latencies: list[float] = []
    nodes: list[float] = []
    nodes_per_second: list[float] = []
    invalid_candidates = invalid_moves = 0

    for match_index, match in enumerate(result.matches):
        primary_side = 0 if match_index % 2 == 0 else 1
        if match.winner == primary_side:
            wins += 1
        invalid_candidates += match.invalid_candidates
        invalid_moves += match.invalid_moves
        latencies.extend(match.decision_latencies_ms)
        nodes.extend(match.search_nodes)
        nodes_per_second.extend(match.search_nodes_per_second)
        for event in match.events:
            if event.player_index != primary_side or event.move is None:
                continue
            pieces += 1
            attacks += int(event.attack > 0)
            sent += event.sent
            cancelled += event.cancelled
            clears += event.lines_cleared
            top_outs += int(event.top_out)
            b2b_values.append(float(event.b2b))
            stack_values.append(float(event.stack_height))

    seconds = max(pieces, 1)
    games = len(result.matches)
    return BenchmarkReport(
        schema_version=1,
        metadata={
            "agent_a": result.agent_a,
            "agent_b": result.agent_b,
            "games": games,
            "seeds": list(result.seeds),
            "preset": result.preset,
            "max_turns": result.max_turns,
            "side_swapped": result.side_swapped,
        },
        metrics={
            "win_rate": wins / max(games, 1),
            "wins": wins,
            "pieces": pieces,
            "apm": attacks * 60.0 / seconds,
            "pps": pieces / seconds,
            "app": sent / seconds,
            "garbage": sent,
            "cancel": cancelled,
            "clear": clears,
            "b2b": sum(b2b_values) / max(len(b2b_values), 1),
            "stack": sum(stack_values) / max(len(stack_values), 1),
            "top_out": top_outs,
            "invalid_candidates": invalid_candidates,
            "invalid_moves": invalid_moves,
            "latency_p50_ms": _percentile(latencies, 50),
            "latency_p95_ms": _percentile(latencies, 95),
            "latency_p99_ms": _percentile(latencies, 99),
            "search_nodes": sum(nodes) / max(len(nodes), 1),
            "search_nodes_per_second": sum(nodes_per_second) / max(len(nodes_per_second), 1),
        },
    )

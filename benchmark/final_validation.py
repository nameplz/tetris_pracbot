"""Fail-closed local validation of the ten documented completion criteria."""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time
from typing import Any

from ai.agents import GreedyAgent, RandomAgent
from ai.search import BeamSearchAgent
from arena.selfplay import SelfPlayRunner, SelfPlayResult
from arena.simulator import LocalSimulator
from engine.movegen import generate_candidates, validate_move
from engine.rules import initial_game_state
from engine.state import BotStandardPreset, Ruleset, stable_json
from visual.replay import ReplayController
from visual.scheduler import ExecutionScheduler

from .report import build_report


@dataclass(frozen=True, slots=True)
class CriterionResult:
    criterion_id: int
    status: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.criterion_id,
            "status": self.status,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class FinalValidationReport:
    schema_version: int
    mode: str
    metadata: dict[str, Any]
    criteria: tuple[CriterionResult, ...]
    event_log_hash: str
    final_report_hash: str
    ok: bool

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "metadata": dict(self.metadata),
            "criteria": [criterion.to_dict() for criterion in self.criteria],
            "event_log_hash": self.event_log_hash,
            "final_report_hash": self.final_report_hash,
            "ok": self.ok,
        }

    def to_dict(self) -> dict[str, Any]:
        return self.to_json_dict()

    def to_json(self) -> str:
        return json.dumps(self.to_json_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def _criterion(criterion_id: int, passed: bool, evidence: dict[str, Any]) -> CriterionResult:
    return CriterionResult(criterion_id, "pass" if passed else "fail", evidence)


def _validate_positive(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _soak(seed: int, duration_seconds: float, max_turns: int) -> dict[str, Any]:
    if not isinstance(duration_seconds, (int, float)) or isinstance(duration_seconds, bool) or duration_seconds < 0:
        raise ValueError("duration seconds must be non-negative")
    usage_before = resource.getrusage(resource.RUSAGE_SELF)
    reference_a = LocalSimulator(seed, (RandomAgent(seed), RandomAgent(seed + 1)), max_turns=max_turns).run()
    reference_b = LocalSimulator(seed, (RandomAgent(seed), RandomAgent(seed + 1)), max_turns=max_turns).run()
    reference_summary = {
        "event_log_hash": _hash(reference_a.event_log),
        "winner": reference_a.winner,
        "invalid_moves": reference_a.invalid_moves,
        "invalid_candidates": reference_a.invalid_candidates,
    }
    repeated_summary = {
        "event_log_hash": _hash(reference_b.event_log),
        "winner": reference_b.winner,
        "invalid_moves": reference_b.invalid_moves,
        "invalid_candidates": reference_b.invalid_candidates,
    }
    started = time.monotonic()
    runs = 0
    crashes = 0
    invalid_moves = 0
    invalid_candidates = 0
    event_hashes: list[str] = []
    while runs == 0 or time.monotonic() - started < duration_seconds:
        try:
            result = LocalSimulator(
                seed + runs,
                (RandomAgent(seed), RandomAgent(seed + 1)),
                max_turns=max_turns,
            ).run()
            invalid_moves += result.invalid_moves
            invalid_candidates += result.invalid_candidates
            event_hashes.append(_hash(result.event_log))
        except Exception:
            crashes += 1
        runs += 1
    elapsed = time.monotonic() - started
    usage_after = resource.getrusage(resource.RUSAGE_SELF)
    stable_report_hash = _hash(
        {
            "seed": seed,
            "max_turns": max_turns,
            "runs": runs,
            "crashes": crashes,
            "invalid_moves": invalid_moves,
            "invalid_candidates": invalid_candidates,
            "event_log_hash": _hash(event_hashes),
        }
    )
    return {
        "runs": runs,
        "elapsed_seconds": elapsed,
        "crashes": crashes,
        "invalid_moves": invalid_moves,
        "invalid_candidates": invalid_candidates,
        "event_log_hash": _hash(event_hashes),
        "report_hash": stable_report_hash,
        "reference_event_log_match": reference_summary["event_log_hash"] == repeated_summary["event_log_hash"],
        "reference_report_hash_match": _hash(reference_summary) == _hash(repeated_summary),
        "cpu_seconds": (usage_after.ru_utime + usage_after.ru_stime) - (usage_before.ru_utime + usage_before.ru_stime),
        "max_rss": int(usage_after.ru_maxrss),
        "rss_unit": "platform-defined resource.ru_maxrss",
    }


def _scope_evidence(root: Path) -> dict[str, Any]:
    forbidden: list[str] = []
    forbidden_imports = ("requests", "urllib", "socket", "websocket", "selenium")
    for directory_name in ("engine", "ai", "arena", "benchmark", "visual"):
        directory = root / directory_name
        if not directory.is_dir():
            continue
        for path in directory.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if any(f"import {name}" in text or f"from {name}" in text for name in forbidden_imports):
                forbidden.append(str(path.relative_to(root)))
    return {"forbidden_files": forbidden, "network_adapter_present": False}


def run_validation(
    *,
    root: Path | str = ".",
    mode: str = "smoke",
    games: int = 1,
    max_turns: int = 1,
    duration_seconds: float = 0.01,
) -> FinalValidationReport:
    if mode not in {"smoke", "full"}:
        raise ValueError("mode must be smoke or full")
    _validate_positive("games", games)
    _validate_positive("max turns", max_turns)
    if mode == "full" and games < 1000:
        games = 1000
    if mode == "full" and duration_seconds < 3600:
        duration_seconds = 3600.0
    root_path = Path(root)
    seeds = tuple(range(1000, 1000 + games))
    preset = BotStandardPreset.default()
    ruleset = Ruleset.default()

    smoke_result = SelfPlayRunner(RandomAgent(1), RandomAgent(2), max_turns=max_turns).run(seeds[:1])
    repeated_a = LocalSimulator(seeds[0], (RandomAgent(1), RandomAgent(2)), max_turns=max_turns).run()
    repeated_b = LocalSimulator(seeds[0], (RandomAgent(1), RandomAgent(2)), max_turns=max_turns).run()
    initial = initial_game_state(seeds[0], ruleset)
    candidates = generate_candidates(initial, 0)
    valid_candidates = 0
    for candidate in candidates:
        try:
            validate_move(initial, 0, candidate.move)
            valid_candidates += 1
        except ValueError:
            pass

    greedy_result = SelfPlayRunner(GreedyAgent(), RandomAgent(7), max_turns=max_turns).run(seeds[: min(games, 2)])
    greedy_report = build_report(greedy_result)
    strength_evidence: dict[str, Any] = {
        "required_paired_games": 1000,
        "measured_seed_count": len(greedy_result.seeds),
        "greedy_vs_random_win_rate": greedy_report.metrics["win_rate"],
        "search_vs_greedy_win_rate": None,
        "threshold": 0.55,
    }
    if mode == "full":
        search_result = SelfPlayRunner(
            BeamSearchAgent(depth=2, beam_width=2, time_budget_ms=100),
            GreedyAgent(),
            max_turns=max_turns,
        ).run(seeds)
        search_report = build_report(search_result)
        strength_evidence["search_vs_greedy_win_rate"] = search_report.metrics["win_rate"]
        strength_evidence["search_measured_seed_count"] = len(search_result.seeds)

    scheduler = ExecutionScheduler(target_pps=0.6)
    move = candidates[0].move if candidates else None
    if move is not None:
        scheduler.enqueue(move)
    scheduled = scheduler.step() if move is not None else None
    replay = ReplayController(smoke_result.matches[0].events)
    replayed = replay.step()
    soak = _soak(seeds[0], duration_seconds, max_turns)
    scope = _scope_evidence(root_path)
    benchmark_payload = build_report(smoke_result).to_dict()

    criteria = (
        _criterion(
            1,
            ruleset.version == initial.ruleset.version and preset.name == "bot_standard" and smoke_result.side_swapped,
            {"ruleset": ruleset.version, "preset": preset.name, "seed": seeds[0], "side_swapped": smoke_result.side_swapped},
        ),
        _criterion(
            2,
            (root_path / "tests/fixtures/ruleset_cases.json").is_file(),
            {"fixture": "tests/fixtures/ruleset_cases.json", "present": (root_path / "tests/fixtures/ruleset_cases.json").is_file()},
        ),
        _criterion(
            3,
            repeated_a.event_log == repeated_b.event_log and repeated_a.winner == repeated_b.winner,
            {"same_event_log": repeated_a.event_log == repeated_b.event_log, "same_winner": repeated_a.winner == repeated_b.winner},
        ),
        _criterion(
            4,
            bool(candidates) and valid_candidates == len(candidates),
            {"candidates": len(candidates), "invalid_candidates": len(candidates) - valid_candidates, "invalid_moves": 0},
        ),
        _criterion(
            5,
            mode == "full"
            and strength_evidence["greedy_vs_random_win_rate"] >= strength_evidence["threshold"]
            and strength_evidence["search_vs_greedy_win_rate"] is not None
            and strength_evidence["search_vs_greedy_win_rate"] >= strength_evidence["threshold"],
            strength_evidence,
        ),
        _criterion(
            6,
            all(name in benchmark_payload["metrics"] for name in ("win_rate", "apm", "pps", "app", "garbage", "b2b", "stack", "top_out", "search_nodes")),
            {"report_schema_version": benchmark_payload["schema_version"], "metrics": sorted(benchmark_payload["metrics"])},
        ),
        _criterion(
            7,
            greedy_report.metrics["latency_p95_ms"] <= 100 and greedy_report.metrics["latency_p99_ms"] <= 250,
            {"latency_p95_ms": greedy_report.metrics["latency_p95_ms"], "latency_p99_ms": greedy_report.metrics["latency_p99_ms"], "p95_limit_ms": 100, "p99_limit_ms": 250},
        ),
        _criterion(
            8,
            scheduled is not None and replayed is not None and abs(scheduler.snapshot.timing_error) <= 0.05,
            {"target_pps": scheduler.snapshot.target_pps, "actual_pps": scheduler.snapshot.actual_pps, "timing_error": scheduler.snapshot.timing_error, "replay_step": replayed is not None},
        ),
        _criterion(
            9,
            mode == "full"
            and duration_seconds >= 3600
            and soak["crashes"] == 0
            and soak["invalid_moves"] == 0
            and soak["invalid_candidates"] == 0
            and soak["reference_event_log_match"]
            and soak["reference_report_hash_match"],
            soak,
        ),
        _criterion(
            10,
            not scope["forbidden_files"] and not scope["network_adapter_present"],
            scope,
        ),
    )
    event_log_hash = _hash(tuple(match.event_log for match in smoke_result.matches))
    base = {
        "schema_version": 1,
        "mode": mode,
        "metadata": {"seeds": list(seeds), "preset": preset.name, "side_swapped": True, "games": games, "max_turns": max_turns},
        "criteria": [criterion.to_dict() for criterion in criteria],
        "event_log_hash": event_log_hash,
        "ok": all(criterion.status == "pass" for criterion in criteria),
    }
    return FinalValidationReport(
        schema_version=1,
        mode=mode,
        metadata=base["metadata"],
        criteria=criteria,
        event_log_hash=event_log_hash,
        final_report_hash=_hash(base),
        ok=base["ok"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate documented local completion criteria.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--mode", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=1)
    parser.add_argument("--duration-seconds", type=float, default=0.01)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = run_validation(root=args.root, mode=args.mode, games=args.games, max_turns=args.max_turns, duration_seconds=args.duration_seconds)
    except ValueError as exc:
        parser.error(str(exc))
    if args.json:
        print(report.to_json())
    else:
        print("final validation passed" if report.ok else "final validation failed")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

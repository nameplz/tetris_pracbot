"""Small CLI for smoke and batch local benchmark runs."""

from __future__ import annotations

import argparse
import json

from ai.agents import GreedyAgent, RandomAgent

from arena.selfplay import SelfPlayRunner

from .report import build_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic local self-play.")
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--mode", choices=("smoke", "batch"), default="smoke")
    args = parser.parse_args()
    if args.games <= 0 or args.max_turns <= 0:
        parser.error("games and max-turns must be positive")
    games = min(args.games, 2) if args.mode == "smoke" else args.games
    seeds = tuple(args.seed + offset for offset in range(games))
    result = SelfPlayRunner(GreedyAgent(), RandomAgent(args.seed), max_turns=args.max_turns).run(seeds)
    print(json.dumps(build_report(result).to_dict(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

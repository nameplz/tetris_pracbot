"""Authoritative deterministic local 1v1 simulator."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import time
from typing import Any, Protocol

from ai.search import BeamSearchAgent
from engine.attack import apply_due_garbage, calculate_attack, resolve_attack
from engine.movegen import Move, generate_candidates, validate_move
from engine.rules import initial_game_state, seven_bag
from engine.state import BotStandardPreset, GameState, Piece, Ruleset, stable_json


class AgentLike(Protocol):
    def choose_move(self, state: GameState, player_index: int = 0) -> Move:
        ...


def _positive_int(name: str, value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _stack_height(state: GameState, player_index: int) -> int:
    board = state.players[player_index].board
    return max(
        (board.total_height - row for row in range(board.total_height) if any(board.cell(row, column) != "." for column in range(board.width))),
        default=0,
    )


@dataclass(frozen=True, slots=True)
class Event:
    seed: int
    ruleset_version: str
    preset: str
    player_index: int
    tick: int
    move: Move | None
    lines_cleared: int = 0
    attack: int = 0
    cancelled: int = 0
    sent: int = 0
    b2b: int = 0
    stack_height: int = 0
    top_out: bool = False
    state_digest: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "ruleset_version": self.ruleset_version,
            "preset": self.preset,
            "player_index": self.player_index,
            "tick": self.tick,
            "move": self.move.to_dict() if self.move else None,
            "lines_cleared": self.lines_cleared,
            "attack": self.attack,
            "cancelled": self.cancelled,
            "sent": self.sent,
            "b2b": self.b2b,
            "stack_height": self.stack_height,
            "top_out": self.top_out,
            "state_digest": self.state_digest,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class MatchResult:
    seed: int
    ruleset_version: str
    preset: str
    agent_names: tuple[str, str]
    winner: int | None
    turns: int
    terminal: bool
    events: tuple[Event, ...]
    invalid_candidates: int
    invalid_moves: int
    decision_latencies_ms: tuple[float, ...]
    search_nodes: tuple[int, ...]
    search_nodes_per_second: tuple[float, ...]

    @property
    def event_log(self) -> tuple[str, ...]:
        return tuple(stable_json(event) for event in self.events)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "ruleset_version": self.ruleset_version,
            "preset": self.preset,
            "agent_names": list(self.agent_names),
            "winner": self.winner,
            "turns": self.turns,
            "terminal": self.terminal,
            "events": [event.to_dict() for event in self.events],
            "invalid_candidates": self.invalid_candidates,
            "invalid_moves": self.invalid_moves,
            "decision_latencies_ms": list(self.decision_latencies_ms),
            "search_nodes": list(self.search_nodes),
            "search_nodes_per_second": list(self.search_nodes_per_second),
        }


class LocalSimulator:
    """Run two snapshot-only agents against one authoritative GameState."""

    def __init__(
        self,
        seed: int,
        agents: tuple[AgentLike, AgentLike],
        *,
        ruleset: Ruleset | None = None,
        preset: BotStandardPreset | None = None,
        max_turns: int = 100,
    ) -> None:
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise ValueError("seed must be an integer")
        if not isinstance(agents, tuple) or len(agents) != 2:
            raise ValueError("agents must contain exactly two agents")
        self.ruleset = ruleset or Ruleset.default()
        self.preset = preset or BotStandardPreset.default()
        self.max_turns = _positive_int("max turns", max_turns)
        self.agents = agents
        self.state = initial_game_state(seed, self.ruleset)
        stream = seven_bag(seed, self.max_turns * 3 + self.ruleset.next_size + 10)
        self._streams: tuple[tuple[Piece, ...], tuple[Piece, ...]] = (stream, stream)
        self._stream_indices = [self.ruleset.next_size + 1, self.ruleset.next_size + 1]
        self._events: list[Event] = []
        self._decision_latencies: list[float] = []
        self._search_nodes: list[int] = []
        self._search_nodes_per_second: list[float] = []
        self._invalid_candidates = 0
        self._invalid_moves = 0

    def _refill_queue(self, state: GameState, player_index: int) -> GameState:
        player = state.players[player_index]
        needed = state.ruleset.next_size - len(player.next_queue)
        if needed <= 0:
            return state
        start = self._stream_indices[player_index]
        end = start + needed
        pieces = self._streams[player_index][start:end]
        self._stream_indices[player_index] = end
        updated = replace(player, next_queue=player.next_queue + pieces)
        players = list(state.players)
        players[player_index] = updated
        return replace(state, players=tuple(players))  # type: ignore[arg-type]

    def _apply_due(self, state: GameState) -> GameState:
        updated = state
        for player_index in range(2):
            updated = apply_due_garbage(updated, player_index)
        return updated

    def _error_event(self, player_index: int, error: str) -> Event:
        player = self.state.players[player_index]
        return Event(
            seed=self.state.seed,
            ruleset_version=self.state.ruleset.version,
            preset=self.preset.name,
            player_index=player_index,
            tick=self.state.tick,
            move=None,
            stack_height=_stack_height(self.state, player_index),
            top_out=player.top_out,
            state_digest=hashlib.sha256(stable_json(self.state).encode("utf-8")).hexdigest(),
            error=error,
        )

    def _choose_move(self, snapshot: GameState, player_index: int) -> Move:
        agent = self.agents[player_index]
        started = time.perf_counter()
        if isinstance(agent, BeamSearchAgent):
            result = agent.search(snapshot, player_index)
            self._search_nodes.append(result.nodes_searched)
            self._search_nodes_per_second.append(result.nodes_per_second)
            move = result.root_move
        else:
            move = agent.choose_move(snapshot, player_index)
        self._decision_latencies.append((time.perf_counter() - started) * 1000.0)
        return move

    def _play_one(self, player_index: int) -> tuple[int | None, bool]:
        snapshot = self.state
        try:
            move = self._choose_move(snapshot, player_index)
            candidate = validate_move(snapshot, player_index, move)
        except (ValueError, TypeError) as exc:
            self._invalid_moves += 1
            self._events.append(self._error_event(player_index, str(exc)))
            return 1 - player_index, True

        player = candidate.state.players[player_index]
        outcome = calculate_attack(
            lines_cleared=candidate.lines_cleared,
            spin_kind=candidate.move.spin_kind,
            combo=player.streak.combo,
            b2b_charging=player.streak.b2b_charging,
            surge=player.streak.surge,
            all_clear=player.streak.all_clear,
            clutch_clear=player.streak.clutch_clear,
        )
        resolved = resolve_attack(candidate.state, player_index, outcome)
        self.state = self._refill_queue(resolved.state, player_index)
        player = self.state.players[player_index]
        event = Event(
            seed=self.state.seed,
            ruleset_version=self.state.ruleset.version,
            preset=self.preset.name,
            player_index=player_index,
            tick=self.state.tick,
            move=candidate.move,
            lines_cleared=candidate.lines_cleared,
            attack=outcome.total_attack,
            cancelled=resolved.cancelled,
            sent=resolved.sent,
            b2b=player.streak.b2b_chain,
            stack_height=_stack_height(self.state, player_index),
            top_out=player.top_out,
            state_digest=hashlib.sha256(stable_json(self.state).encode("utf-8")).hexdigest(),
        )
        self._events.append(event)
        if player.top_out:
            return 1 - player_index, True
        return None, False

    def run(self) -> MatchResult:
        winner: int | None = None
        terminal = False
        for turn in range(self.max_turns):
            self.state = self._apply_due(self.state)
            top_out_players = tuple(index for index, player in enumerate(self.state.players) if player.top_out)
            if top_out_players:
                winner = 1 - top_out_players[0] if len(top_out_players) == 1 else None
                terminal = True
                break
            winner, terminal = self._play_one(turn % 2)
            if terminal:
                break
        return MatchResult(
            seed=self.state.seed,
            ruleset_version=self.state.ruleset.version,
            preset=self.preset.name,
            agent_names=tuple(type(agent).__name__ for agent in self.agents),  # type: ignore[return-value]
            winner=winner,
            turns=len(self._events),
            terminal=terminal,
            events=tuple(self._events),
            invalid_candidates=self._invalid_candidates,
            invalid_moves=self._invalid_moves,
            decision_latencies_ms=tuple(self._decision_latencies),
            search_nodes=tuple(self._search_nodes),
            search_nodes_per_second=tuple(self._search_nodes_per_second),
        )

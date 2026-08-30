"""Reachable Move generation and path validation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from .rules import (
    Placement,
    can_place,
    classify_t_spin,
    hard_drop,
    hold_current_piece,
    lock_piece,
    piece_cells,
    rotate_placement,
)
from .state import GameState, Piece, Board


ActionName = str
VALID_ACTIONS = frozenset(("left", "right", "rotate_cw", "rotate_ccw", "soft_drop", "hard_drop"))
SEARCH_ACTIONS = ("left", "right", "rotate_cw", "rotate_ccw", "soft_drop")


def _check_int(name: str, value: object, minimum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class Move:
    use_hold: bool
    piece: Piece
    rotation: int
    x: int
    y: int
    spin_kind: str = "none"
    input_path: tuple[ActionName, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.use_hold, bool):
            raise ValueError("use_hold must be a boolean")
        if not isinstance(self.piece, Piece):
            raise ValueError("move piece must be a Piece")
        rotation = _check_int("move rotation", self.rotation, minimum=0)
        if rotation > 3 or rotation != self.piece.rotation:
            raise ValueError("move rotation must match piece rotation between 0 and 3")
        _check_int("move x", self.x)
        _check_int("move y", self.y, minimum=0)
        if self.spin_kind not in {"none", "mini", "full"}:
            raise ValueError("move spin_kind must be none, mini, or full")
        path = tuple(self.input_path)
        if not all(isinstance(action, str) and action in VALID_ACTIONS for action in path):
            raise ValueError("input_path contains an invalid action")
        if not path or path[-1] != "hard_drop":
            raise ValueError("input_path must end with hard_drop")
        object.__setattr__(self, "input_path", path)

    @property
    def signature(self) -> tuple[bool, str, int, int, int, str]:
        return (self.use_hold, self.piece.kind, self.rotation, self.x, self.y, self.spin_kind)

    def to_dict(self) -> dict[str, Any]:
        return {
            "use_hold": self.use_hold,
            "piece": self.piece.to_dict(),
            "rotation": self.rotation,
            "x": self.x,
            "y": self.y,
            "spin_kind": self.spin_kind,
            "input_path": list(self.input_path),
        }


@dataclass(frozen=True, slots=True)
class Candidate:
    move: Move
    state: GameState
    path_cost: int
    lines_cleared: int

    def __post_init__(self) -> None:
        if not isinstance(self.move, Move):
            raise ValueError("candidate move must be a Move")
        if not isinstance(self.state, GameState):
            raise ValueError("candidate state must be a GameState")
        _check_int("candidate path cost", self.path_cost, minimum=1)
        _check_int("candidate lines cleared", self.lines_cleared, minimum=0)

    @property
    def signature(self) -> tuple[bool, str, int, int, int, str]:
        return self.move.signature

    def to_dict(self) -> dict[str, Any]:
        return {
            "move": self.move.to_dict(),
            "state": self.state.to_dict(),
            "path_cost": self.path_cost,
            "lines_cleared": self.lines_cleared,
        }


def _spawn(board: Board, piece: Piece) -> Placement:
    return Placement(piece=Piece(piece.kind), x=(board.width - 4) // 2, y=0)


def _next_state(board: Board, placement: Placement, action: ActionName) -> Placement | None:
    if action == "left":
        candidate = Placement(placement.piece, placement.x - 1, placement.y, placement.rotated)
        return candidate if can_place(board, candidate) else None
    if action == "right":
        candidate = Placement(placement.piece, placement.x + 1, placement.y, placement.rotated)
        return candidate if can_place(board, candidate) else None
    if action == "soft_drop":
        candidate = Placement(placement.piece, placement.x, placement.y + 1, placement.rotated)
        return candidate if can_place(board, candidate) else None
    if action == "rotate_cw":
        return rotate_placement(board, placement, clockwise=True)
    if action == "rotate_ccw":
        return rotate_placement(board, placement, clockwise=False)
    raise ValueError(f"unsupported movement action: {action}")


def _reachable_landings(board: Board, piece: Piece) -> tuple[tuple[Placement, tuple[ActionName, ...]], ...]:
    start = _spawn(board, piece)
    if not can_place(board, start):
        return ()
    pending: deque[tuple[Placement, tuple[ActionName, ...]]] = deque([(start, ())])
    visited = {(start.piece.kind, start.piece.rotation, start.x, start.y)}
    landings: dict[tuple[int, int, int, bool], tuple[Placement, tuple[ActionName, ...]]] = {}
    while pending:
        current, path = pending.popleft()
        landing = hard_drop(board, current.piece, x=current.x, y=current.y)
        landing = Placement(
            piece=landing.piece,
            x=landing.x,
            y=landing.y,
            rotated=current.rotated,
        )
        key = (landing.piece.rotation, landing.x, landing.y, landing.rotated)
        landings.setdefault(key, (landing, path + ("hard_drop",)))
        for action in SEARCH_ACTIONS:
            next_placement = _next_state(board, current, action)
            if next_placement is None:
                continue
            visit_key = (
                next_placement.piece.kind,
                next_placement.piece.rotation,
                next_placement.x,
                next_placement.y,
            )
            if visit_key not in visited:
                visited.add(visit_key)
                pending.append((next_placement, path + (action,)))
    return tuple(sorted(landings.values(), key=lambda item: (item[0].piece.rotation, item[0].x, item[0].y, item[1])))


def _branch_state(state: GameState, player_index: int, use_hold: bool) -> tuple[GameState, Piece] | None:
    if not use_hold:
        return state, state.players[player_index].current_piece
    if not state.ruleset.hold_enabled or state.players[player_index].hold_used:
        return None
    try:
        held_state = hold_current_piece(state, player_index)
    except ValueError:
        return None
    return held_state, held_state.players[player_index].current_piece


def generate_candidates(state: GameState, player_index: int = 0) -> tuple[Candidate, ...]:
    player_index = _check_int("player index", player_index, minimum=0)
    if player_index >= len(state.players):
        raise ValueError("player index out of range")
    branches = [(False, state, state.players[player_index].current_piece)]
    held = _branch_state(state, player_index, True)
    if held is not None:
        branches.append((True, held[0], held[1]))

    candidates: list[Candidate] = []
    for use_hold, branch_state, piece in branches:
        board = branch_state.players[player_index].board
        for landing, path in _reachable_landings(board, piece):
            spin_kind = classify_t_spin(
                board,
                landing.piece,
                x=landing.x,
                y=landing.y,
                rotated=landing.rotated,
            )
            move = Move(
                use_hold=use_hold,
                piece=landing.piece,
                rotation=landing.piece.rotation,
                x=landing.x,
                y=landing.y,
                spin_kind=spin_kind,
                input_path=path,
            )
            result = lock_piece(branch_state, player_index, landing)
            candidates.append(
                Candidate(
                    move=move,
                    state=result.state,
                    path_cost=len(path),
                    lines_cleared=result.lines_cleared,
                )
            )
    return tuple(sorted(candidates, key=lambda candidate: (candidate.move.signature, candidate.move.input_path)))


def replay_path(board: Board, piece: Piece, input_path: tuple[ActionName, ...]) -> Placement:
    path = tuple(input_path)
    if not path or path[-1] != "hard_drop":
        raise ValueError("input_path must end with hard_drop")
    current = _spawn(board, piece)
    if not can_place(board, current):
        raise ValueError("piece cannot spawn on board")
    for index, action in enumerate(path):
        if action == "hard_drop":
            if index != len(path) - 1:
                raise ValueError("hard_drop must be the final action")
            landing = hard_drop(board, current.piece, x=current.x, y=current.y)
            return Placement(landing.piece, landing.x, landing.y, current.rotated)
        if action not in SEARCH_ACTIONS:
            raise ValueError(f"invalid action at path index {index}: {action}")
        next_placement = _next_state(board, current, action)
        if next_placement is None:
            raise ValueError(f"action is not legal at path index {index}: {action}")
        current = next_placement
    raise ValueError("input_path did not produce a placement")


def validate_move(state: GameState, player_index: int, move: Move) -> Candidate:
    if not isinstance(move, Move):
        raise ValueError("move must be a Move")
    player_index = _check_int("player index", player_index, minimum=0)
    if player_index >= len(state.players):
        raise ValueError("player index out of range")
    branch = _branch_state(state, player_index, move.use_hold)
    if branch is None:
        raise ValueError("Move Hold branch is not legal")
    branch_state, piece = branch
    replayed = replay_path(branch_state.players[player_index].board, piece, move.input_path)
    if (replayed.piece.kind, replayed.piece.rotation, replayed.x, replayed.y) != (
        move.piece.kind,
        move.rotation,
        move.x,
        move.y,
    ):
        raise ValueError("Move placement does not match input path")
    candidates = generate_candidates(state, player_index)
    for candidate in candidates:
        if candidate.move.signature == move.signature:
            return candidate
    raise ValueError("Move is not a reachable Candidate")

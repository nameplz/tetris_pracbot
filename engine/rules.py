"""Pure board, piece, and deterministic rules transitions."""

from __future__ import annotations

from dataclasses import dataclass, replace
import random
from typing import Any

from .state import GameState, Piece, PlayerState, Ruleset, Board, PIECE_KINDS


Coord = tuple[int, int]
SpinKind = str
SPIN_KINDS = frozenset(("none", "mini", "full"))


PIECE_SHAPES: dict[str, tuple[tuple[Coord, ...], ...]] = {
    "I": (
        ((0, 1), (1, 1), (2, 1), (3, 1)),
        ((2, 0), (2, 1), (2, 2), (2, 3)),
        ((0, 2), (1, 2), (2, 2), (3, 2)),
        ((1, 0), (1, 1), (1, 2), (1, 3)),
    ),
    "O": (((1, 0), (2, 0), (1, 1), (2, 1)),) * 4,
    "T": (
        ((1, 0), (0, 1), (1, 1), (2, 1)),
        ((1, 0), (1, 1), (2, 1), (1, 2)),
        ((0, 1), (1, 1), (2, 1), (1, 2)),
        ((1, 0), (0, 1), (1, 1), (1, 2)),
    ),
    "J": (
        ((0, 0), (0, 1), (1, 1), (2, 1)),
        ((1, 0), (2, 0), (1, 1), (1, 2)),
        ((0, 1), (1, 1), (2, 1), (2, 2)),
        ((1, 0), (1, 1), (0, 2), (1, 2)),
    ),
    "L": (
        ((2, 0), (0, 1), (1, 1), (2, 1)),
        ((1, 0), (1, 1), (1, 2), (2, 2)),
        ((0, 1), (1, 1), (2, 1), (0, 2)),
        ((0, 0), (1, 0), (1, 1), (1, 2)),
    ),
    "S": (
        ((1, 0), (2, 0), (0, 1), (1, 1)),
        ((1, 0), (1, 1), (2, 1), (2, 2)),
        ((1, 1), (2, 1), (0, 2), (1, 2)),
        ((0, 0), (0, 1), (1, 1), (1, 2)),
    ),
    "Z": (
        ((0, 0), (1, 0), (1, 1), (2, 1)),
        ((2, 0), (1, 1), (2, 1), (1, 2)),
        ((0, 1), (1, 1), (1, 2), (2, 2)),
        ((1, 0), (0, 1), (1, 1), (0, 2)),
    ),
}


JLSTZ_KICKS: dict[tuple[int, int], tuple[Coord, ...]] = {
    (0, 1): ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)),
    (1, 0): ((0, 0), (1, 0), (1, 1), (0, -2), (1, -2)),
    (1, 2): ((0, 0), (1, 0), (1, 1), (0, -2), (1, -2)),
    (2, 1): ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)),
    (2, 3): ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),
    (3, 2): ((0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)),
    (3, 0): ((0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)),
    (0, 3): ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),
}
I_KICKS: dict[tuple[int, int], tuple[Coord, ...]] = {
    (0, 1): ((0, 0), (-2, 0), (1, 0), (-2, 1), (1, -2)),
    (1, 0): ((0, 0), (2, 0), (-1, 0), (2, -1), (-1, 2)),
    (1, 2): ((0, 0), (-1, 0), (2, 0), (-1, -2), (2, 1)),
    (2, 1): ((0, 0), (1, 0), (-2, 0), (1, 2), (-2, -1)),
    (2, 3): ((0, 0), (2, 0), (-1, 0), (2, -1), (-1, 2)),
    (3, 2): ((0, 0), (-2, 0), (1, 0), (-2, 1), (1, -2)),
    (3, 0): ((0, 0), (1, 0), (-2, 0), (1, 2), (-2, -1)),
    (0, 3): ((0, 0), (-1, 0), (2, 0), (-1, -2), (2, 1)),
}


def _check_int(name: str, value: object, minimum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class Placement:
    piece: Piece
    x: int
    y: int
    rotated: bool = False
    spin_kind: SpinKind = "none"

    def __post_init__(self) -> None:
        if not isinstance(self.piece, Piece):
            raise ValueError("placement piece must be a Piece")
        _check_int("placement x", self.x)
        _check_int("placement y", self.y)
        if self.spin_kind not in SPIN_KINDS:
            raise ValueError("placement spin_kind must be none, mini, or full")
        if not isinstance(self.rotated, bool):
            raise ValueError("placement rotated must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "piece": self.piece.to_dict(),
            "x": self.x,
            "y": self.y,
            "rotated": self.rotated,
            "spin_kind": self.spin_kind,
        }


@dataclass(frozen=True, slots=True)
class LockResult:
    state: GameState
    lines_cleared: int
    spin_kind: SpinKind
    all_clear: bool
    top_out: bool


def piece_cells(
    piece_or_placement: Piece | Placement,
    x: int | None = None,
    y: int | None = None,
) -> tuple[Coord, ...]:
    if isinstance(piece_or_placement, Placement):
        piece = piece_or_placement.piece
        x = piece_or_placement.x
        y = piece_or_placement.y
    else:
        piece = piece_or_placement
    if not isinstance(piece, Piece):
        raise ValueError("piece must be a Piece or Placement")
    if x is None or y is None:
        raise ValueError("x and y are required for a Piece")
    _check_int("x", x)
    _check_int("y", y)
    return tuple((x + cell_x, y + cell_y) for cell_x, cell_y in PIECE_SHAPES[piece.kind][piece.rotation])


def can_place(board: Board, placement: Placement) -> bool:
    for x, y in piece_cells(placement):
        if x < 0 or x >= board.width or y < 0 or y >= board.total_height:
            return False
        if board.cell(y, x) != ".":
            return False
    return True


def hard_drop(board: Board, piece: Piece, *, x: int, y: int = 0) -> Placement:
    placement = Placement(piece=piece, x=x, y=y)
    if not can_place(board, placement):
        raise ValueError("piece cannot spawn at requested position")
    while can_place(board, replace(placement, y=placement.y + 1)):
        placement = replace(placement, y=placement.y + 1)
    return placement


def rotate_placement(board: Board, placement: Placement, *, clockwise: bool = True) -> Placement | None:
    direction = 1 if clockwise else -1
    old_rotation = placement.piece.rotation
    new_rotation = (old_rotation + direction) % 4
    rotated_piece = Piece(placement.piece.kind, new_rotation)
    if placement.piece.kind == "O":
        kicks = ((0, 0),)
    elif placement.piece.kind == "I":
        kicks = I_KICKS[(old_rotation, new_rotation)]
    else:
        kicks = JLSTZ_KICKS[(old_rotation, new_rotation)]
    for offset_x, offset_y in kicks:
        candidate = Placement(
            piece=rotated_piece,
            x=placement.x + offset_x,
            y=placement.y + offset_y,
            rotated=True,
        )
        if can_place(board, candidate):
            return candidate
    return None


def _occupied_or_outside(board: Board, x: int, y: int) -> bool:
    return x < 0 or x >= board.width or y < 0 or y >= board.total_height or board.cell(y, x) != "."


def classify_t_spin(
    board: Board,
    piece: Piece,
    *,
    x: int,
    y: int,
    rotated: bool,
) -> SpinKind:
    if piece.kind != "T" or not rotated:
        return "none"
    pivot_x, pivot_y = x + 1, y + 1
    corners = sum(
        _occupied_or_outside(board, pivot_x + dx, pivot_y + dy)
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1))
    )
    if corners >= 3:
        return "full"
    if corners == 2:
        return "mini"
    return "none"


def seven_bag(seed: int, count: int) -> tuple[Piece, ...]:
    _check_int("seed", seed)
    count = _check_int("piece count", count, minimum=0)
    rng = random.Random(seed)
    result: list[Piece] = []
    while len(result) < count:
        bag = list(PIECE_KINDS)
        rng.shuffle(bag)
        result.extend(Piece(kind) for kind in bag)
    return tuple(result[:count])


def initial_game_state(seed: int, ruleset: Ruleset | None = None) -> GameState:
    selected_ruleset = ruleset or Ruleset.default()
    sequence = seven_bag(seed, selected_ruleset.next_size + 1)
    player = PlayerState(current_piece=sequence[0], next_queue=sequence[1:])
    return GameState(seed=seed, ruleset=selected_ruleset, players=(player, player))


def place_piece(board: Board, placement: Placement) -> Board:
    if not can_place(board, placement):
        raise ValueError("placement is not legal on board")
    rows = [list(row) for row in board.cells]
    for x, y in piece_cells(placement):
        rows[y][x] = placement.piece.kind
    return board.with_cells(tuple(tuple(row) for row in rows))


def clear_full_lines(board: Board) -> tuple[Board, int]:
    remaining = [row for row in board.cells if "." in row]
    cleared = board.total_height - len(remaining)
    empty_rows = [tuple("." for _ in range(board.width)) for _ in range(cleared)]
    return board.with_cells(tuple(empty_rows + remaining)), cleared


def is_top_out(board: Board) -> bool:
    return any(cell != "." for row in board.cells[: board.buffer_height] for cell in row)


def hold_current_piece(state: GameState, player_index: int) -> GameState:
    player_index = _check_int("player index", player_index, minimum=0)
    if player_index >= len(state.players):
        raise ValueError("player index out of range")
    player = state.players[player_index]
    if not state.ruleset.hold_enabled:
        raise ValueError("Hold is disabled by Ruleset")
    if player.hold_used:
        raise ValueError("Hold already used before lock")
    queue = player.next_queue
    if player.hold_piece is None:
        if not queue:
            raise ValueError("cannot Hold without a queued replacement piece")
        current = Piece(queue[0].kind)
        next_queue = queue[1:]
        held = Piece(player.current_piece.kind)
    else:
        current = Piece(player.hold_piece.kind)
        next_queue = queue
        held = Piece(player.current_piece.kind)
    updated = replace(player, current_piece=current, hold_piece=held, next_queue=next_queue, hold_used=True)
    players = list(state.players)
    players[player_index] = updated
    return replace(state, players=tuple(players))  # type: ignore[arg-type]


def lock_piece(state: GameState, player_index: int, placement: Placement) -> LockResult:
    player_index = _check_int("player index", player_index, minimum=0)
    if player_index >= len(state.players):
        raise ValueError("player index out of range")
    player = state.players[player_index]
    if player.top_out:
        raise ValueError("cannot lock a top-out player")
    if placement.piece.kind != player.current_piece.kind:
        raise ValueError("placement piece does not match current piece")
    placed = place_piece(player.board, placement)
    cleared_board, lines_cleared = clear_full_lines(placed)
    spin_kind = placement.spin_kind
    if spin_kind == "none":
        spin_kind = classify_t_spin(
            player.board,
            placement.piece,
            x=placement.x,
            y=placement.y,
            rotated=placement.rotated,
        )
    next_queue = player.next_queue
    next_piece = next_queue[0] if next_queue else player.current_piece
    remaining_queue = next_queue[1:] if next_queue else ()
    updated_streak = replace(
        player.streak,
        combo=player.streak.combo + 1 if lines_cleared else -1,
        all_clear=all(cell == "." for row in cleared_board.cells for cell in row),
        clutch_clear=lines_cleared > 0 and is_top_out(player.board),
    )
    updated = replace(
        player,
        board=cleared_board,
        current_piece=Piece(next_piece.kind),
        next_queue=remaining_queue,
        streak=updated_streak,
        hold_used=False,
        top_out=is_top_out(cleared_board),
    )
    players = list(state.players)
    players[player_index] = updated
    next_state = replace(state, players=tuple(players), tick=state.tick + 1)  # type: ignore[arg-type]
    return LockResult(
        state=next_state,
        lines_cleared=lines_cleared,
        spin_kind=spin_kind,
        all_clear=updated.streak.all_clear,
        top_out=updated.top_out,
    )

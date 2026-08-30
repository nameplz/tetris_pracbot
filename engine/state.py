"""Immutable state values shared by the local rules engine and AI."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
import json
from typing import Any


PIECE_KINDS = ("I", "J", "L", "O", "S", "T", "Z")
CELL_VALUES = frozenset((".", "I", "J", "L", "O", "S", "T", "Z", "X"))
DEFAULT_RULESET_VERSION = "tetrio-public-2026-08-30"
DEFAULT_BUFFER_HEIGHT = 4
DEFAULT_NEXT_SIZE = 5
DEFAULT_BAG_SIZE = 7


def _check_int(name: str, value: object, *, minimum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _check_non_empty(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


@dataclass(frozen=True, slots=True)
class Board:
    """10-column board with a visible projection and minimal buffer rows."""

    width: int = 10
    visible_height: int = 20
    buffer_height: int = DEFAULT_BUFFER_HEIGHT
    cells: tuple[tuple[str, ...], ...] = ()

    def __post_init__(self) -> None:
        width = _check_int("board width", self.width, minimum=1)
        visible_height = _check_int("visible height", self.visible_height, minimum=1)
        buffer_height = _check_int("buffer height", self.buffer_height, minimum=0)
        if width != 10:
            raise ValueError("board width must be 10")
        if visible_height != 20:
            raise ValueError("visible height must be 20")

        expected_rows = visible_height + buffer_height
        normalized = self.cells
        if not normalized:
            normalized = tuple(tuple("." for _ in range(width)) for _ in range(expected_rows))
        else:
            normalized = tuple(tuple(row) for row in normalized)
        if len(normalized) != expected_rows:
            raise ValueError(f"board must contain {expected_rows} rows")
        for row_index, row in enumerate(normalized):
            if len(row) != width:
                raise ValueError(f"board row {row_index} must contain {width} cells")
            if any(cell not in CELL_VALUES for cell in row):
                raise ValueError(f"board row {row_index} contains an invalid cell")
        object.__setattr__(self, "cells", normalized)

    @classmethod
    def empty(cls) -> Board:
        return cls()

    @property
    def total_height(self) -> int:
        return self.visible_height + self.buffer_height

    @property
    def visible_rows(self) -> tuple[tuple[str, ...], ...]:
        return self.cells[self.buffer_height :]

    def cell(self, row: int, column: int) -> str:
        row = _check_int("row", row, minimum=0)
        column = _check_int("column", column, minimum=0)
        if row >= self.total_height or column >= self.width:
            raise ValueError("board coordinate out of range")
        return self.cells[row][column]

    def with_cells(self, cells: tuple[tuple[str, ...], ...]) -> Board:
        return Board(
            width=self.width,
            visible_height=self.visible_height,
            buffer_height=self.buffer_height,
            cells=cells,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "visible_height": self.visible_height,
            "buffer_height": self.buffer_height,
            "cells": ["".join(row) for row in self.cells],
        }


@dataclass(frozen=True, slots=True)
class Piece:
    kind: str
    rotation: int = 0

    def __post_init__(self) -> None:
        if self.kind not in PIECE_KINDS:
            raise ValueError(f"piece kind must be one of {PIECE_KINDS}")
        rotation = _check_int("piece rotation", self.rotation, minimum=0)
        if rotation > 3:
            raise ValueError("piece rotation must be between 0 and 3")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "rotation": self.rotation}


@dataclass(frozen=True, slots=True)
class GarbagePacket:
    lines: int
    hole: int
    arrival_tick: int

    def __post_init__(self) -> None:
        _check_int("garbage lines", self.lines, minimum=1)
        hole = _check_int("garbage hole", self.hole, minimum=0)
        if hole >= 10:
            raise ValueError("garbage hole must be between 0 and 9")
        _check_int("garbage arrival tick", self.arrival_tick, minimum=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lines": self.lines,
            "hole": self.hole,
            "arrival_tick": self.arrival_tick,
        }


@dataclass(frozen=True, slots=True)
class StreakState:
    combo: int = -1
    b2b_chain: int = 0
    b2b_charging: bool = False
    surge: int = 0
    opener_active: bool = True
    all_clear: bool = False
    clutch_clear: bool = False

    def __post_init__(self) -> None:
        _check_int("combo", self.combo, minimum=-1)
        _check_int("B2B chain", self.b2b_chain, minimum=0)
        _check_int("surge", self.surge, minimum=0)
        for name, value in (
            ("b2b_charging", self.b2b_charging),
            ("opener_active", self.opener_active),
            ("all_clear", self.all_clear),
            ("clutch_clear", self.clutch_clear),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "combo": self.combo,
            "b2b_chain": self.b2b_chain,
            "b2b_charging": self.b2b_charging,
            "surge": self.surge,
            "opener_active": self.opener_active,
            "all_clear": self.all_clear,
            "clutch_clear": self.clutch_clear,
        }


@dataclass(frozen=True, slots=True)
class Ruleset:
    """Versioned public/observable rule snapshot."""

    version: str = DEFAULT_RULESET_VERSION
    source: str = "public-observable-project-scope"
    fixture_sources: tuple[str, ...] = (
        "docs/TETR.IO AI Bot 기획서 v1.3.md",
        "docs/completion-criteria.md",
    )
    supported_scope: tuple[str, ...] = (
        "7-bag",
        "hold",
        "next",
        "hard-drop",
        "srs-plus",
        "spin",
        "all-mini-plus",
        "line-clear",
        "garbage",
        "attack",
        "combo",
        "b2b-charging",
        "surge",
        "opener-phase",
        "all-clear",
        "clutch-clear",
        "top-out",
    )
    visible_width: int = 10
    visible_height: int = 20
    buffer_height: int = DEFAULT_BUFFER_HEIGHT
    bag_size: int = DEFAULT_BAG_SIZE
    next_size: int = DEFAULT_NEXT_SIZE
    hold_enabled: bool = True
    hard_drop_enabled: bool = True
    rotation_system: str = "SRS+"
    gravity: float = 0.0
    lock_delay_ms: int = 500
    garbage_multiplier: float = 1.0
    garbage_increase: int = 0
    passthrough: bool = False
    b2b_charging: bool = True
    combo_multiplier: bool = True
    opener_phase: bool = True
    clutch_clear: bool = True

    def __post_init__(self) -> None:
        _check_non_empty("ruleset version", self.version)
        _check_non_empty("ruleset source", self.source)
        fixture_sources = tuple(self.fixture_sources)
        supported_scope = tuple(self.supported_scope)
        if not fixture_sources or not all(isinstance(item, str) and item.strip() for item in fixture_sources):
            raise ValueError("fixture_sources must contain non-empty strings")
        if not supported_scope or not all(isinstance(item, str) and item.strip() for item in supported_scope):
            raise ValueError("supported_scope must contain non-empty strings")
        object.__setattr__(self, "fixture_sources", fixture_sources)
        object.__setattr__(self, "supported_scope", supported_scope)

        if self.visible_width != 10:
            raise ValueError("visible width must be 10")
        if self.visible_height != 20:
            raise ValueError("visible height must be 20")
        _check_int("buffer height", self.buffer_height, minimum=0)
        if self.bag_size != DEFAULT_BAG_SIZE:
            raise ValueError("ruleset bag size must be 7")
        if self.next_size != DEFAULT_NEXT_SIZE:
            raise ValueError("ruleset NEXT size must be 5")
        if self.rotation_system != "SRS+":
            raise ValueError("ruleset rotation system must be SRS+")
        for name, value in (
            ("hold_enabled", self.hold_enabled),
            ("hard_drop_enabled", self.hard_drop_enabled),
            ("passthrough", self.passthrough),
            ("b2b_charging", self.b2b_charging),
            ("combo_multiplier", self.combo_multiplier),
            ("opener_phase", self.opener_phase),
            ("clutch_clear", self.clutch_clear),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be a boolean")
        if self.gravity != 0.0:
            raise ValueError("Bot Standard Preset gravity must be 0G")
        _check_int("lock delay", self.lock_delay_ms, minimum=1)
        if not isinstance(self.garbage_multiplier, (int, float)) or isinstance(
            self.garbage_multiplier, bool
        ) or self.garbage_multiplier <= 0:
            raise ValueError("garbage multiplier must be positive")
        _check_int("garbage increase", self.garbage_increase, minimum=0)

    @classmethod
    def default(cls) -> Ruleset:
        return cls()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "source": self.source,
            "fixture_sources": list(self.fixture_sources),
            "supported_scope": list(self.supported_scope),
            "visible_width": self.visible_width,
            "visible_height": self.visible_height,
            "buffer_height": self.buffer_height,
            "bag_size": self.bag_size,
            "next_size": self.next_size,
            "hold_enabled": self.hold_enabled,
            "hard_drop_enabled": self.hard_drop_enabled,
            "rotation_system": self.rotation_system,
            "gravity": self.gravity,
            "lock_delay_ms": self.lock_delay_ms,
            "garbage_multiplier": self.garbage_multiplier,
            "garbage_increase": self.garbage_increase,
            "passthrough": self.passthrough,
            "b2b_charging": self.b2b_charging,
            "combo_multiplier": self.combo_multiplier,
            "opener_phase": self.opener_phase,
            "clutch_clear": self.clutch_clear,
        }


@dataclass(frozen=True, slots=True)
class BotStandardPreset:
    """Single settings profile shared by training, benchmark, and bot runtime."""

    name: str = "bot_standard"
    visible_width: int = 10
    visible_height: int = 20
    bag_size: int = DEFAULT_BAG_SIZE
    next_size: int = DEFAULT_NEXT_SIZE
    hold_enabled: bool = True
    hard_drop_enabled: bool = True
    rotation_system: str = "SRS+"
    gravity: float = 0.0
    gravity_increase: int = 0
    lock_delay_ms: int = 500
    garbage_multiplier: float = 1.0
    garbage_increase: int = 0
    passthrough: bool = False
    b2b_charging: bool = True
    combo_multiplier: bool = True
    opener_phase: bool = True
    clutch_clear: bool = True

    def __post_init__(self) -> None:
        _check_non_empty("preset name", self.name)
        if self.visible_width != 10 or self.visible_height != 20:
            raise ValueError("Bot Standard Preset board must be 10x20")
        if self.bag_size != DEFAULT_BAG_SIZE or self.next_size != DEFAULT_NEXT_SIZE:
            raise ValueError("Bot Standard Preset must use 7-bag and NEXT 5")
        if self.rotation_system != "SRS+" or self.gravity != 0.0:
            raise ValueError("Bot Standard Preset must use SRS+ and 0G")
        for name, value in (
            ("hold_enabled", self.hold_enabled),
            ("hard_drop_enabled", self.hard_drop_enabled),
            ("passthrough", self.passthrough),
            ("b2b_charging", self.b2b_charging),
            ("combo_multiplier", self.combo_multiplier),
            ("opener_phase", self.opener_phase),
            ("clutch_clear", self.clutch_clear),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be a boolean")
        _check_int("gravity increase", self.gravity_increase, minimum=0)
        _check_int("lock delay", self.lock_delay_ms, minimum=1)
        if not isinstance(self.garbage_multiplier, (int, float)) or isinstance(
            self.garbage_multiplier, bool
        ) or self.garbage_multiplier <= 0:
            raise ValueError("garbage multiplier must be positive")
        _check_int("garbage increase", self.garbage_increase, minimum=0)

    @classmethod
    def default(cls) -> BotStandardPreset:
        return cls()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "visible_width": self.visible_width,
            "visible_height": self.visible_height,
            "bag_size": self.bag_size,
            "next_size": self.next_size,
            "hold_enabled": self.hold_enabled,
            "hard_drop_enabled": self.hard_drop_enabled,
            "rotation_system": self.rotation_system,
            "gravity": self.gravity,
            "gravity_increase": self.gravity_increase,
            "lock_delay_ms": self.lock_delay_ms,
            "garbage_multiplier": self.garbage_multiplier,
            "garbage_increase": self.garbage_increase,
            "passthrough": self.passthrough,
            "b2b_charging": self.b2b_charging,
            "combo_multiplier": self.combo_multiplier,
            "opener_phase": self.opener_phase,
            "clutch_clear": self.clutch_clear,
        }


@dataclass(frozen=True, slots=True)
class PlayerState:
    board: Board = field(default_factory=Board.empty)
    current_piece: Piece = field(default_factory=lambda: Piece("I"))
    hold_piece: Piece | None = None
    next_queue: tuple[Piece, ...] = ()
    garbage_queue: tuple[GarbagePacket, ...] = ()
    streak: StreakState = field(default_factory=StreakState)
    hold_used: bool = False
    top_out: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.board, Board):
            raise ValueError("player board must be a Board")
        if not isinstance(self.current_piece, Piece):
            raise ValueError("current piece must be a Piece")
        if self.hold_piece is not None and not isinstance(self.hold_piece, Piece):
            raise ValueError("hold piece must be a Piece or None")
        next_queue = tuple(self.next_queue)
        garbage_queue = tuple(self.garbage_queue)
        if len(next_queue) > DEFAULT_NEXT_SIZE:
            raise ValueError("NEXT queue cannot exceed 5 pieces")
        if not all(isinstance(piece, Piece) for piece in next_queue):
            raise ValueError("NEXT queue must contain Pieces")
        if not all(isinstance(packet, GarbagePacket) for packet in garbage_queue):
            raise ValueError("garbage queue must contain GarbagePackets")
        if not isinstance(self.streak, StreakState):
            raise ValueError("streak must be a StreakState")
        if not isinstance(self.hold_used, bool) or not isinstance(self.top_out, bool):
            raise ValueError("hold_used and top_out must be booleans")
        object.__setattr__(self, "next_queue", next_queue)
        object.__setattr__(self, "garbage_queue", garbage_queue)

    @classmethod
    def empty(cls) -> PlayerState:
        return cls()

    def to_dict(self) -> dict[str, Any]:
        return {
            "board": self.board.to_dict(),
            "current_piece": self.current_piece.to_dict(),
            "hold_piece": self.hold_piece.to_dict() if self.hold_piece else None,
            "next_queue": [piece.to_dict() for piece in self.next_queue],
            "garbage_queue": [packet.to_dict() for packet in self.garbage_queue],
            "streak": self.streak.to_dict(),
            "hold_used": self.hold_used,
            "top_out": self.top_out,
        }


@dataclass(frozen=True, slots=True)
class GameState:
    """Authoritative immutable match snapshot consumed by Agents."""

    seed: int
    ruleset: Ruleset
    players: tuple[PlayerState, PlayerState]
    tick: int = 0

    def __post_init__(self) -> None:
        _check_int("seed", self.seed)
        if not isinstance(self.ruleset, Ruleset):
            raise ValueError("ruleset must be a Ruleset")
        players = tuple(self.players)
        if len(players) != 2:
            raise ValueError("GameState requires exactly two players")
        if not all(isinstance(player, PlayerState) for player in players):
            raise ValueError("players must contain PlayerState values")
        _check_int("tick", self.tick, minimum=0)
        object.__setattr__(self, "players", players)  # type: ignore[arg-type]

    @classmethod
    def empty(cls, seed: int, ruleset: Ruleset | None = None) -> GameState:
        selected_ruleset = ruleset or Ruleset.default()
        empty_player = PlayerState.empty()
        return cls(seed=seed, ruleset=selected_ruleset, players=(empty_player, empty_player))

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "ruleset": self.ruleset.to_dict(),
            "players": [player.to_dict() for player in self.players],
            "tick": self.tick,
        }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _jsonable(value.to_dict())
    if is_dataclass(value):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def stable_json(value: Any) -> str:
    """Serialize a state value with byte-stable key and collection ordering."""

    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

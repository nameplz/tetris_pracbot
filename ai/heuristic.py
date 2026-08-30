"""Pure board evaluation for the baseline AI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.attack import calculate_attack
from engine.movegen import Candidate
from engine.state import Board, GameState


def _metric(name: str, value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class FeatureVector:
    holes: int = 0
    covered_holes: int = 0
    stack_height: int = 0
    bumpiness: int = 0
    wells: int = 0
    top_out_risk: int = 0
    lines_cleared: int = 0
    attack: int = 0
    cancel: int = 0
    combo: int = 0
    b2b: int = 0
    surge: int = 0
    all_clear: int = 0
    clutch_clear: int = 0
    incoming_garbage: int = 0
    opponent_pressure: int = 0

    def __post_init__(self) -> None:
        for name, value in self.to_dict().items():
            _metric(name, value)

    @property
    def garbage_cancel(self) -> int:
        return self.cancel

    @property
    def b2b_chain(self) -> int:
        return self.b2b

    def to_dict(self) -> dict[str, int]:
        return {
            "holes": self.holes,
            "covered_holes": self.covered_holes,
            "stack_height": self.stack_height,
            "bumpiness": self.bumpiness,
            "wells": self.wells,
            "top_out_risk": self.top_out_risk,
            "lines_cleared": self.lines_cleared,
            "attack": self.attack,
            "cancel": self.cancel,
            "combo": self.combo,
            "b2b": self.b2b,
            "surge": self.surge,
            "all_clear": self.all_clear,
            "clutch_clear": self.clutch_clear,
            "incoming_garbage": self.incoming_garbage,
            "opponent_pressure": self.opponent_pressure,
        }


@dataclass(frozen=True, slots=True)
class WeightSet:
    holes: float = -8.0
    covered_holes: float = -12.0
    stack_height: float = -1.5
    bumpiness: float = -0.8
    wells: float = -1.0
    top_out_risk: float = -1000.0
    lines_cleared: float = 1.0
    attack: float = 4.0
    cancel: float = 2.0
    combo: float = 0.5
    b2b: float = 1.5
    surge: float = 0.25
    all_clear: float = 3.0
    clutch_clear: float = 1.0
    incoming_garbage: float = -5.0
    opponent_pressure: float = 0.25

    @classmethod
    def bot_standard(cls) -> WeightSet:
        return cls()

    def to_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in FeatureVector().to_dict()}


@dataclass(frozen=True, slots=True)
class Evaluation:
    score: float
    features: FeatureVector
    breakdown: tuple[tuple[str, float], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "features": self.features.to_dict(),
            "breakdown": {name: value for name, value in self.breakdown},
        }


def _column_heights(board: Board) -> tuple[int, ...]:
    heights: list[int] = []
    for column in range(board.width):
        first = next((row for row in range(board.total_height) if board.cell(row, column) != "."), None)
        heights.append(0 if first is None else board.total_height - first)
    return tuple(heights)


def _board_features(board: Board) -> tuple[int, int, int, int, int, int]:
    heights = _column_heights(board)
    holes = 0
    covered = 0
    for column in range(board.width):
        seen_block = False
        for row in range(board.total_height):
            cell = board.cell(row, column)
            if cell != ".":
                seen_block = True
            elif seen_block:
                holes += 1
                if row > 0 and board.cell(row - 1, column) != ".":
                    covered += 1
    bumpiness = sum(abs(left - right) for left, right in zip(heights, heights[1:]))
    wells = 0
    for column, height in enumerate(heights):
        left = heights[column - 1] if column else board.total_height
        right = heights[column + 1] if column + 1 < board.width else board.total_height
        wells += max(0, min(left, right) - height)
    stack_height = max(heights, default=0)
    buffer_cells = sum(cell != "." for row in board.cells[: board.buffer_height] for cell in row)
    return holes, covered, stack_height, bumpiness, wells, buffer_cells


def extract_features(candidate: Candidate, player_index: int = 0) -> FeatureVector:
    """Extract immutable, serializable features from a candidate result."""

    if not isinstance(candidate, Candidate):
        raise ValueError("candidate must be a Candidate")
    if not isinstance(player_index, int) or isinstance(player_index, bool) or player_index not in (0, 1):
        raise ValueError("player index must be 0 or 1")

    player = candidate.state.players[player_index]
    opponent = candidate.state.players[1 - player_index]
    holes, covered, height, bumpiness, wells, buffer_cells = _board_features(player.board)
    streak = player.streak
    attack = calculate_attack(
        lines_cleared=candidate.lines_cleared,
        spin_kind=candidate.move.spin_kind,
        combo=streak.combo,
        b2b_charging=streak.b2b_charging,
        surge=streak.surge,
        all_clear=streak.all_clear,
        clutch_clear=streak.clutch_clear,
    )
    incoming = sum(packet.lines for packet in player.garbage_queue)
    opponent_height = _column_heights(opponent.board)
    opponent_pressure = max(opponent_height, default=0) + sum(
        packet.lines for packet in opponent.garbage_queue
    )
    return FeatureVector(
        holes=holes,
        covered_holes=covered,
        stack_height=height,
        bumpiness=bumpiness,
        wells=wells,
        top_out_risk=1 if player.top_out else buffer_cells,
        lines_cleared=candidate.lines_cleared,
        attack=attack.total_attack,
        cancel=min(attack.total_attack, incoming),
        combo=max(0, streak.combo),
        b2b=streak.b2b_chain,
        surge=streak.surge,
        all_clear=int(streak.all_clear),
        clutch_clear=int(streak.clutch_clear),
        incoming_garbage=incoming,
        opponent_pressure=opponent_pressure,
    )


@dataclass(frozen=True, slots=True)
class HeuristicEvaluator:
    """Weighted evaluator with a stable, inspectable breakdown."""

    weights: WeightSet = field(default_factory=WeightSet.bot_standard)

    def evaluate_features(self, features: FeatureVector) -> float:
        if not isinstance(features, FeatureVector):
            raise ValueError("features must be a FeatureVector")
        return sum(getattr(self.weights, name) * value for name, value in features.to_dict().items())

    def evaluate(self, candidate: Candidate, player_index: int = 0) -> Evaluation:
        features = extract_features(candidate, player_index)
        breakdown = tuple(
            (name, getattr(self.weights, name) * value)
            for name, value in features.to_dict().items()
        )
        return Evaluation(score=sum(value for _, value in breakdown), features=features, breakdown=breakdown)

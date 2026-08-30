"""Deterministic attack and garbage transitions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .rules import _check_int
from .state import Board, GarbagePacket, GameState


LINE_ATTACK = (0, 0, 1, 2, 4)
MINI_SPIN_ATTACK = (0, 0, 1, 2, 0)
FULL_SPIN_ATTACK = (0, 2, 4, 6, 8)


@dataclass(frozen=True, slots=True)
class AttackOutcome:
    lines_cleared: int
    spin_kind: str
    base_attack: int
    combo_bonus: int
    b2b_bonus: int
    surge_bonus: int
    all_clear_bonus: int
    clutch_clear_bonus: int
    total_attack: int
    qualifies_b2b: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "lines_cleared": self.lines_cleared,
            "spin_kind": self.spin_kind,
            "base_attack": self.base_attack,
            "combo_bonus": self.combo_bonus,
            "b2b_bonus": self.b2b_bonus,
            "surge_bonus": self.surge_bonus,
            "all_clear_bonus": self.all_clear_bonus,
            "clutch_clear_bonus": self.clutch_clear_bonus,
            "total_attack": self.total_attack,
            "qualifies_b2b": self.qualifies_b2b,
        }


@dataclass(frozen=True, slots=True)
class GarbageResolution:
    state: GameState
    cancelled: int
    sent: int


def calculate_attack(
    *,
    lines_cleared: int,
    spin_kind: str = "none",
    combo: int = -1,
    b2b_charging: bool = False,
    surge: int = 0,
    all_clear: bool = False,
    clutch_clear: bool = False,
) -> AttackOutcome:
    lines_cleared = _check_int("lines cleared", lines_cleared, minimum=0)
    if lines_cleared > 4:
        raise ValueError("lines cleared cannot exceed 4")
    if spin_kind not in {"none", "mini", "full"}:
        raise ValueError("spin kind must be none, mini, or full")
    combo = _check_int("combo", combo, minimum=-1)
    surge = _check_int("surge", surge, minimum=0)
    if not isinstance(b2b_charging, bool):
        raise ValueError("b2b_charging must be a boolean")
    if not isinstance(all_clear, bool) or not isinstance(clutch_clear, bool):
        raise ValueError("clear flags must be booleans")

    table = {
        "none": LINE_ATTACK,
        "mini": MINI_SPIN_ATTACK,
        "full": FULL_SPIN_ATTACK,
    }[spin_kind]
    base_attack = table[lines_cleared]
    qualifies_b2b = spin_kind in {"mini", "full"} or lines_cleared == 4
    b2b_bonus = 1 if b2b_charging and qualifies_b2b and base_attack else 0
    combo_bonus = max(0, combo) // 2
    surge_bonus = surge // 2
    all_clear_bonus = 10 if all_clear else 0
    clutch_clear_bonus = 1 if clutch_clear else 0
    total_attack = sum(
        (base_attack, combo_bonus, b2b_bonus, surge_bonus, all_clear_bonus, clutch_clear_bonus)
    )
    return AttackOutcome(
        lines_cleared=lines_cleared,
        spin_kind=spin_kind,
        base_attack=base_attack,
        combo_bonus=combo_bonus,
        b2b_bonus=b2b_bonus,
        surge_bonus=surge_bonus,
        all_clear_bonus=all_clear_bonus,
        clutch_clear_bonus=clutch_clear_bonus,
        total_attack=total_attack,
        qualifies_b2b=qualifies_b2b,
    )


def enqueue_garbage(
    state: GameState,
    target_player: int,
    *,
    lines: int,
    arrival_tick: int | None = None,
    hole: int | None = None,
) -> GameState:
    target_player = _check_int("target player", target_player, minimum=0)
    if target_player >= len(state.players):
        raise ValueError("target player out of range")
    lines = _check_int("garbage lines", lines, minimum=1)
    selected_tick = state.tick + 1 if arrival_tick is None else _check_int(
        "garbage arrival tick", arrival_tick, minimum=0
    )
    selected_hole = (
        (state.seed + state.tick + target_player * 7 + len(state.players[target_player].garbage_queue))
        % state.ruleset.visible_width
        if hole is None
        else _check_int("garbage hole", hole, minimum=0)
    )
    if selected_hole >= state.ruleset.visible_width:
        raise ValueError("garbage hole out of range")
    packet = GarbagePacket(lines=lines, hole=selected_hole, arrival_tick=selected_tick)
    player = state.players[target_player]
    updated = replace(player, garbage_queue=player.garbage_queue + (packet,))
    players = list(state.players)
    players[target_player] = updated
    return replace(state, players=tuple(players))  # type: ignore[arg-type]


def _cancel_packets(packets: tuple[GarbagePacket, ...], amount: int) -> tuple[tuple[GarbagePacket, ...], int]:
    remaining = amount
    updated: list[GarbagePacket] = []
    cancelled = 0
    for packet in packets:
        if remaining <= 0:
            updated.append(packet)
            continue
        removed = min(packet.lines, remaining)
        cancelled += removed
        remaining -= removed
        if packet.lines > removed:
            updated.append(replace(packet, lines=packet.lines - removed))
    return tuple(updated), cancelled


def resolve_attack(state: GameState, player_index: int, outcome: AttackOutcome) -> GarbageResolution:
    player_index = _check_int("player index", player_index, minimum=0)
    if player_index >= len(state.players):
        raise ValueError("player index out of range")
    if not isinstance(outcome, AttackOutcome):
        raise ValueError("outcome must be an AttackOutcome")

    attacker = state.players[player_index]
    remaining_queue, cancelled = _cancel_packets(attacker.garbage_queue, outcome.total_attack)
    sent = outcome.total_attack - cancelled
    updated_streak = replace(
        attacker.streak,
        b2b_chain=attacker.streak.b2b_chain + 1 if outcome.qualifies_b2b and outcome.total_attack else 0,
        b2b_charging=outcome.qualifies_b2b,
        surge=attacker.streak.surge + (1 if outcome.total_attack else 0),
        opener_active=False if outcome.lines_cleared else attacker.streak.opener_active,
    )
    updated_attacker = replace(attacker, garbage_queue=remaining_queue, streak=updated_streak)
    players = list(state.players)
    players[player_index] = updated_attacker
    if sent:
        target = 1 - player_index
        target_player = players[target]
        hole = (state.seed + state.tick + player_index * 7 + len(target_player.garbage_queue)) % state.ruleset.visible_width
        packet = GarbagePacket(lines=sent, hole=hole, arrival_tick=state.tick + 1)
        players[target] = replace(target_player, garbage_queue=target_player.garbage_queue + (packet,))
    return GarbageResolution(state=replace(state, players=tuple(players)), cancelled=cancelled, sent=sent)


def apply_garbage(board: Board, packet: GarbagePacket) -> Board:
    if packet.hole >= board.width:
        raise ValueError("garbage hole out of range for board")
    garbage_row = tuple("." if column == packet.hole else "X" for column in range(board.width))
    incoming = [garbage_row for _ in range(packet.lines)]
    if len(incoming) >= board.total_height:
        return board.with_cells(tuple(incoming[-board.total_height :]))
    return board.with_cells(tuple(list(board.cells[len(incoming) :]) + incoming))


def apply_due_garbage(state: GameState, player_index: int) -> GameState:
    player_index = _check_int("player index", player_index, minimum=0)
    if player_index >= len(state.players):
        raise ValueError("player index out of range")
    player = state.players[player_index]
    due = tuple(packet for packet in player.garbage_queue if packet.arrival_tick <= state.tick)
    pending = tuple(packet for packet in player.garbage_queue if packet.arrival_tick > state.tick)
    board = player.board
    for packet in due:
        board = apply_garbage(board, packet)
    updated = replace(player, board=board, garbage_queue=pending, top_out=any(
        cell != "." for row in board.cells[: board.buffer_height] for cell in row
    ))
    players = list(state.players)
    players[player_index] = updated
    return replace(state, players=tuple(players))  # type: ignore[arg-type]

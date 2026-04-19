"""Infer opponent last move from board snapshots (ported verbatim from v2)."""
from __future__ import annotations

from enum import Enum, auto

from game.board import Board
from game.enums import MoveType
from game.move import Move


class OpponentCategory(Enum):
    PLAIN = auto()
    PRIME = auto()
    CARPET = auto()
    SEARCH = auto()


def parse_search_tuple(raw: tuple[object, object] | None) -> tuple[tuple[int, int] | None, bool | None]:
    if not isinstance(raw, tuple) or len(raw) != 2:
        return None, None
    loc, result = raw
    if not (isinstance(loc, tuple) and len(loc) == 2):
        loc = None
    if result not in (True, False, None):
        result = None
    return loc, result


def _fingerprints_equal(a: Board, b: Board, *, include_search_channels: bool = True) -> bool:
    base_equal = (
        a._space_mask == b._space_mask
        and a._primed_mask == b._primed_mask
        and a._carpet_mask == b._carpet_mask
        and a._blocked_mask == b._blocked_mask
        and a.player_worker.get_location() == b.player_worker.get_location()
        and a.opponent_worker.get_location() == b.opponent_worker.get_location()
        and a.player_worker.get_points() == b.player_worker.get_points()
        and a.opponent_worker.get_points() == b.opponent_worker.get_points()
        and a.turn_count == b.turn_count
        and a.is_player_a_turn == b.is_player_a_turn
    )
    if not include_search_channels:
        return base_equal
    return base_equal and a.opponent_search == b.opponent_search and a.player_search == b.player_search


def _category_from_move(move: Move) -> OpponentCategory:
    if move.move_type == MoveType.SEARCH:
        return OpponentCategory.SEARCH
    if move.move_type == MoveType.PRIME:
        return OpponentCategory.PRIME
    if move.move_type == MoveType.CARPET:
        return OpponentCategory.CARPET
    return OpponentCategory.PLAIN


def infer_opponent_category(
    snap_before_our_last_move: Board | None,
    our_last_move: Move | None,
    board_now: Board,
) -> OpponentCategory | None:
    if snap_before_our_last_move is None or our_last_move is None:
        return None

    b0 = snap_before_our_last_move.get_copy()
    if not b0.apply_move(our_last_move, check_ok=True):
        return None
    b0.reverse_perspective()

    loc_now, res_now = parse_search_tuple(board_now.opponent_search)
    loc_snap, res_snap = parse_search_tuple(snap_before_our_last_move.opponent_search)
    if loc_now is not None and res_now in (True, False):
        if (loc_now, res_now) != (loc_snap, res_snap):
            return OpponentCategory.SEARCH

    candidates: list[Move] = []
    seen: set[tuple] = set()
    for mv in b0.get_valid_moves(enemy=False, exclude_search=False):
        if not b0.is_valid_move(mv):
            continue
        key = (mv.move_type, mv.direction, mv.roll_length, mv.search_loc)
        if key not in seen:
            seen.add(key)
            candidates.append(mv)

    def sort_key(m: Move) -> tuple:
        if m.move_type == MoveType.SEARCH:
            return (3, m.search_loc[1], m.search_loc[0])
        if m.move_type == MoveType.CARPET:
            return (2, int(m.direction), m.roll_length)
        if m.move_type == MoveType.PRIME:
            return (1, int(m.direction), 0)
        return (0, int(m.direction), 0)

    candidates.sort(key=sort_key)

    matches: list[Move] = []
    for mv in candidates:
        sim = b0.get_copy()
        if not sim.apply_move(mv, check_ok=True):
            continue
        sim.reverse_perspective()
        if mv.move_type == MoveType.SEARCH:
            sim.opponent_worker.points = board_now.opponent_worker.get_points()
            sim.player_worker.points = board_now.player_worker.get_points()
        if _fingerprints_equal(sim, board_now, include_search_channels=False):
            matches.append(mv)

    if len(matches) == 1:
        return _category_from_move(matches[0])
    return None

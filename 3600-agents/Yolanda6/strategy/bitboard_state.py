from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from game.board import Board
from game.enums import BOARD_SIZE, CARPET_POINTS_TABLE, Cell, Direction, MoveType
from game.move import Move


BOARD_CELLS = BOARD_SIZE * BOARD_SIZE
DIRECTIONS: tuple[Direction, Direction, Direction, Direction] = (
    Direction.UP,
    Direction.RIGHT,
    Direction.DOWN,
    Direction.LEFT,
)
BIT_MASKS: tuple[int, ...] = tuple(1 << idx for idx in range(BOARD_CELLS))
INDEX_TO_LOC: tuple[tuple[int, int], ...] = tuple((idx % BOARD_SIZE, idx // BOARD_SIZE) for idx in range(BOARD_CELLS))
NEIGHBORS_BY_DIR: tuple[dict[Direction, int | None], ...] = tuple(
    {
        Direction.UP: idx - BOARD_SIZE if idx // BOARD_SIZE > 0 else None,
        Direction.RIGHT: idx + 1 if idx % BOARD_SIZE < BOARD_SIZE - 1 else None,
        Direction.DOWN: idx + BOARD_SIZE if idx // BOARD_SIZE < BOARD_SIZE - 1 else None,
        Direction.LEFT: idx - 1 if idx % BOARD_SIZE > 0 else None,
    }
    for idx in range(BOARD_CELLS)
)


def _ray_from(idx: int, direction: Direction):
    cur = idx
    while True:
        cur = NEIGHBORS_BY_DIR[cur][direction]
        if cur is None:
            break
        yield cur


RAYS_BY_DIR: tuple[dict[Direction, tuple[int, ...]], ...] = tuple(
    {
        direction: tuple(_ray_from(idx, direction))
        for direction in DIRECTIONS
    }
    for idx in range(BOARD_CELLS)
)


def loc_to_index(loc: tuple[int, int]) -> int:
    return loc[1] * BOARD_SIZE + loc[0]


def index_to_loc(index: int) -> tuple[int, int]:
    return INDEX_TO_LOC[index]


def move_signature(move: Move) -> tuple[int, int | None, int, tuple[int, int] | None]:
    return (int(move.move_type), int(move.direction) if move.direction is not None else None, move.roll_length, move.search_loc)


def move_immediate_points(move: Move) -> float:
    if move.move_type == MoveType.PRIME:
        return 1.0
    if move.move_type == MoveType.CARPET:
        return float(CARPET_POINTS_TABLE[min(move.roll_length, BOARD_SIZE - 1)])
    return 0.0


def direction_axis(direction: Direction | None) -> str | None:
    if direction in (Direction.LEFT, Direction.RIGHT):
        return "horizontal"
    if direction in (Direction.UP, Direction.DOWN):
        return "vertical"
    return None


@dataclass(slots=True)
class BitboardState:
    """Mutable shadow state used by Yolanda6 search and spatial analysis."""

    space_mask: int
    primed_mask: int
    carpet_mask: int
    blocked_mask: int
    player_idx: int
    opponent_idx: int
    player_points: int
    opponent_points: int
    player_turns_left: int
    opponent_turns_left: int
    turn_count: int

    def current_bit(self) -> int:
        return BIT_MASKS[self.player_idx]

    def player_loc(self) -> tuple[int, int]:
        return INDEX_TO_LOC[self.player_idx]

    def opponent_loc(self) -> tuple[int, int]:
        return INDEX_TO_LOC[self.opponent_idx]

    def worker_mask(self) -> int:
        return BIT_MASKS[self.player_idx] | BIT_MASKS[self.opponent_idx]

    def cell_type(self, idx: int) -> Cell:
        bit = BIT_MASKS[idx]
        if self.primed_mask & bit:
            return Cell.PRIMED
        if self.carpet_mask & bit:
            return Cell.CARPET
        if self.blocked_mask & bit:
            return Cell.BLOCKED
        return Cell.SPACE

    def is_space(self, idx: int) -> bool:
        return bool(self.space_mask & BIT_MASKS[idx])

    def is_plain_destination_open(self, idx: int) -> bool:
        if idx == self.player_idx or idx == self.opponent_idx:
            return False
        bit = BIT_MASKS[idx]
        return not bool((self.blocked_mask | self.primed_mask) & bit)

    def is_legal_non_search_move(self, move: Move) -> bool:
        if move.move_type == MoveType.PLAIN:
            nxt = NEIGHBORS_BY_DIR[self.player_idx][move.direction]
            return nxt is not None and self.is_plain_destination_open(nxt)

        if move.move_type == MoveType.PRIME:
            nxt = NEIGHBORS_BY_DIR[self.player_idx][move.direction]
            if nxt is None or not self.is_plain_destination_open(nxt):
                return False
            return self.is_space(self.player_idx)

        if move.move_type != MoveType.CARPET:
            return False
        if move.roll_length < 1 or move.roll_length > BOARD_SIZE - 1:
            return False
        steps = 0
        for idx in RAYS_BY_DIR[self.player_idx][move.direction]:
            steps += 1
            if idx == self.opponent_idx:
                return False
            if not (self.primed_mask & BIT_MASKS[idx]):
                return False
            if steps == move.roll_length:
                return True
        return False

    def destination_idx(self, move: Move) -> int:
        if move.move_type in (MoveType.PLAIN, MoveType.PRIME):
            nxt = NEIGHBORS_BY_DIR[self.player_idx][move.direction]
            if nxt is None:
                return self.player_idx
            return nxt
        if move.move_type == MoveType.CARPET:
            cur = self.player_idx
            for _ in range(move.roll_length):
                nxt = NEIGHBORS_BY_DIR[cur][move.direction]
                if nxt is None:
                    return cur
                cur = nxt
            return cur
        return self.player_idx

    def valid_non_search_moves(self) -> list[Move]:
        moves: list[Move] = []
        current_is_space = self.is_space(self.player_idx)
        for direction in DIRECTIONS:
            nxt = NEIGHBORS_BY_DIR[self.player_idx][direction]
            if nxt is not None and self.is_plain_destination_open(nxt):
                moves.append(Move.plain(direction))
                if current_is_space:
                    moves.append(Move.prime(direction))
            roll = 0
            for ray_idx in RAYS_BY_DIR[self.player_idx][direction]:
                if ray_idx == self.opponent_idx or not (self.primed_mask & BIT_MASKS[ray_idx]):
                    break
                roll += 1
                moves.append(Move.carpet(direction, roll))
        return moves

    def apply_move(self, move: Move) -> tuple[int, ...] | None:
        if not self.is_legal_non_search_move(move):
            return None

        token = (
            self.space_mask,
            self.primed_mask,
            self.carpet_mask,
            self.blocked_mask,
            self.player_idx,
            self.opponent_idx,
            self.player_points,
            self.opponent_points,
            self.player_turns_left,
            self.opponent_turns_left,
            self.turn_count,
        )

        if move.move_type == MoveType.PLAIN:
            self.player_idx = self.destination_idx(move)
        elif move.move_type == MoveType.PRIME:
            cur_bit = BIT_MASKS[self.player_idx]
            self.space_mask &= ~cur_bit
            self.primed_mask |= cur_bit
            self.player_points += 1
            self.player_idx = self.destination_idx(move)
        elif move.move_type == MoveType.CARPET:
            cur = self.player_idx
            for _ in range(move.roll_length):
                cur = NEIGHBORS_BY_DIR[cur][move.direction]
                cur_bit = BIT_MASKS[cur]
                self.primed_mask &= ~cur_bit
                self.carpet_mask |= cur_bit
            self.player_points += CARPET_POINTS_TABLE[min(move.roll_length, BOARD_SIZE - 1)]
            self.player_idx = cur

        self.player_turns_left -= 1
        self.turn_count += 1

        (
            self.player_idx,
            self.opponent_idx,
            self.player_points,
            self.opponent_points,
            self.player_turns_left,
            self.opponent_turns_left,
        ) = (
            self.opponent_idx,
            self.player_idx,
            self.opponent_points,
            self.player_points,
            self.opponent_turns_left,
            self.player_turns_left,
        )
        return token

    def restore(self, token: tuple[int, ...]) -> None:
        (
            self.space_mask,
            self.primed_mask,
            self.carpet_mask,
            self.blocked_mask,
            self.player_idx,
            self.opponent_idx,
            self.player_points,
            self.opponent_points,
            self.player_turns_left,
            self.opponent_turns_left,
            self.turn_count,
        ) = token


class BitboardAdapter:
    """Translate engine Boards into the lightweight bitboard search state."""

    @staticmethod
    def from_board(board: Board) -> BitboardState:
        return BitboardState(
            space_mask=board._space_mask,
            primed_mask=board._primed_mask,
            carpet_mask=board._carpet_mask,
            blocked_mask=board._blocked_mask,
            player_idx=loc_to_index(board.player_worker.get_location()),
            opponent_idx=loc_to_index(board.opponent_worker.get_location()),
            player_points=board.player_worker.get_points(),
            opponent_points=board.opponent_worker.get_points(),
            player_turns_left=board.player_worker.turns_left,
            opponent_turns_left=board.opponent_worker.turns_left,
            turn_count=board.turn_count,
        )


def abstract_successors(state: BitboardState, idx: int, other_idx: int) -> tuple[int, ...]:
    """One-turn successor positions under root-state movement rules."""
    next_positions: list[int] = []
    for direction in DIRECTIONS:
        nxt = NEIGHBORS_BY_DIR[idx][direction]
        if nxt is not None:
            bit = BIT_MASKS[nxt]
            if nxt != other_idx and not ((state.blocked_mask | state.primed_mask) & bit):
                next_positions.append(nxt)
        for ray_idx in RAYS_BY_DIR[idx][direction]:
            if ray_idx == other_idx or not (state.primed_mask & BIT_MASKS[ray_idx]):
                break
            next_positions.append(ray_idx)
    if not next_positions:
        return ()
    return tuple(dict.fromkeys(next_positions))


def shortest_turn_distances(state: BitboardState, start_idx: int, other_idx: int) -> list[int]:
    dist = [-1] * BOARD_CELLS
    dist[start_idx] = 0
    queue: deque[int] = deque([start_idx])
    while queue:
        cur = queue.popleft()
        nd = dist[cur] + 1
        for nxt in abstract_successors(state, cur, other_idx):
            if dist[nxt] != -1:
                continue
            dist[nxt] = nd
            queue.append(nxt)
    return dist


def shortest_turn_distance(state: BitboardState, start_idx: int, target_idx: int, other_idx: int) -> int | None:
    if start_idx == target_idx:
        return 0
    distances = shortest_turn_distances(state, start_idx, other_idx)
    return None if distances[target_idx] < 0 else distances[target_idx]


def count_exits_with_masks(
    blocked_mask: int,
    primed_mask: int,
    idx: int,
    other_idx: int | None = None,
) -> tuple[int, int]:
    exits = 0
    space_exits = 0
    for direction in DIRECTIONS:
        nxt = NEIGHBORS_BY_DIR[idx][direction]
        if nxt is None or nxt == other_idx:
            continue
        bit = BIT_MASKS[nxt]
        if (blocked_mask | primed_mask) & bit:
            continue
        exits += 1
        if not (blocked_mask & bit):
            space_exits += 1
    return exits, space_exits


def landing_exit_profile_after_carpet(
    state: BitboardState,
    start_idx: int,
    direction: Direction,
    length: int,
    other_idx: int,
) -> tuple[int, int]:
    new_primed = state.primed_mask
    cur = start_idx
    for _ in range(length):
        nxt = NEIGHBORS_BY_DIR[cur][direction]
        if nxt is None:
            break
        new_primed &= ~BIT_MASKS[nxt]
        cur = nxt
    return count_exits_with_masks(state.blocked_mask, new_primed, cur, other_idx)


def adjacent_primed_chain_length(state: BitboardState, entry_idx: int, direction: Direction) -> int:
    length = 0
    for idx in RAYS_BY_DIR[entry_idx][direction]:
        if not (state.primed_mask & BIT_MASKS[idx]):
            break
        length += 1
    return length


def collect_chain_entries(state: BitboardState, min_chain_len: int = 2) -> list[tuple[int, Direction, int, int]]:
    """Return (entry_idx, direction, length, landing_idx) for every adjacent primed chain."""
    entries: list[tuple[int, Direction, int, int]] = []
    for idx in range(BOARD_CELLS):
        bit = BIT_MASKS[idx]
        if (state.blocked_mask | state.primed_mask) & bit:
            continue
        for direction in DIRECTIONS:
            length = 0
            landing_idx = idx
            for ray_idx in RAYS_BY_DIR[idx][direction]:
                if ray_idx == state.player_idx or ray_idx == state.opponent_idx:
                    break
                if not (state.primed_mask & BIT_MASKS[ray_idx]):
                    break
                length += 1
                landing_idx = ray_idx
            if length >= min_chain_len:
                entries.append((idx, direction, length, landing_idx))
    return entries

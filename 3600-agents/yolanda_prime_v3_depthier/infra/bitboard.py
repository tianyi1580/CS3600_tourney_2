"""Bitboard state + move generation for Yolanda Prime v3.

The engine already stores the board as 64-bit masks; we reuse the same
`idx = y * 8 + x` convention. All state transitions are pure-functional:
returning a new `BBState` for Zobrist / TT friendliness."""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Tuple

import numpy as np

from game.board import Board
from game.enums import BOARD_SIZE, CARPET_POINTS_TABLE, Cell, Direction, MoveType
from game.move import Move

# ---------------------------------------------------------------------------
# Precomputed adjacency, ray and inter-cell distance tables.
# ---------------------------------------------------------------------------

NUM_CELLS = BOARD_SIZE * BOARD_SIZE
_DIRECTIONS = (Direction.UP, Direction.RIGHT, Direction.DOWN, Direction.LEFT)
NUM_DIR = 4
_DIR_DXDY: Tuple[Tuple[int, int], ...] = (
    (0, -1),  # UP
    (1, 0),   # RIGHT
    (0, 1),   # DOWN
    (-1, 0),  # LEFT
)


def coord_to_idx(x: int, y: int) -> int:
    return y * BOARD_SIZE + x


def idx_to_coord(i: int) -> Tuple[int, int]:
    return (i % BOARD_SIZE, i // BOARD_SIZE)


def _popcount(mask: int) -> int:
    return bin(mask & ((1 << NUM_CELLS) - 1)).count("1")


def _build_adj() -> list[int]:
    adj = [0] * NUM_CELLS
    for idx in range(NUM_CELLS):
        x, y = idx_to_coord(idx)
        mask = 0
        for dx, dy in _DIR_DXDY:
            nx, ny = x + dx, y + dy
            if 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE:
                mask |= 1 << coord_to_idx(nx, ny)
        adj[idx] = mask
    return adj


def _build_rays() -> tuple[list[list[int]], list[list[tuple[int, ...]]]]:
    """RAY[idx][d] = bitmask of all cells along dir d from idx to the edge (excl origin).
    RAY_SEQ[idx][d] = tuple of cell indices in order along dir d.
    """
    ray_mask: list[list[int]] = [[0] * NUM_DIR for _ in range(NUM_CELLS)]
    ray_seq: list[list[tuple[int, ...]]] = [[tuple() for _ in range(NUM_DIR)] for _ in range(NUM_CELLS)]
    for idx in range(NUM_CELLS):
        x, y = idx_to_coord(idx)
        for d, (dx, dy) in enumerate(_DIR_DXDY):
            seq: list[int] = []
            mask = 0
            nx, ny = x + dx, y + dy
            while 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE:
                nidx = coord_to_idx(nx, ny)
                seq.append(nidx)
                mask |= 1 << nidx
                nx += dx
                ny += dy
            ray_mask[idx][d] = mask
            ray_seq[idx][d] = tuple(seq)
    return ray_mask, ray_seq


def _build_step_neighbor() -> list[list[int]]:
    """NEIGHBOR[idx][d] = neighbor cell index in direction d, or -1 off-board."""
    nbrs = [[-1] * NUM_DIR for _ in range(NUM_CELLS)]
    for idx in range(NUM_CELLS):
        x, y = idx_to_coord(idx)
        for d, (dx, dy) in enumerate(_DIR_DXDY):
            nx, ny = x + dx, y + dy
            if 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE:
                nbrs[idx][d] = coord_to_idx(nx, ny)
    return nbrs


def _build_l1_matrix() -> np.ndarray:
    mat = np.zeros((NUM_CELLS, NUM_CELLS), dtype=np.int16)
    for i in range(NUM_CELLS):
        xi, yi = idx_to_coord(i)
        for j in range(NUM_CELLS):
            xj, yj = idx_to_coord(j)
            mat[i, j] = abs(xi - xj) + abs(yi - yj)
    return mat


ADJ: tuple[int, ...] = tuple(_build_adj())
_RAY_MASK_LIST, _RAY_SEQ_LIST = _build_rays()
RAY: tuple[tuple[int, ...], ...] = tuple(tuple(row) for row in _RAY_MASK_LIST)
RAY_SEQ: tuple[tuple[tuple[int, ...], ...], ...] = tuple(tuple(row) for row in _RAY_SEQ_LIST)
_STEP_LIST = _build_step_neighbor()
NEIGHBOR: tuple[tuple[int, ...], ...] = tuple(tuple(row) for row in _STEP_LIST)
L1: np.ndarray = _build_l1_matrix()
FULL_MASK = (1 << NUM_CELLS) - 1

CARPET_POINTS_LUT: tuple[int, ...] = tuple(
    CARPET_POINTS_TABLE.get(k, -10_000) for k in range(BOARD_SIZE + 1)
)


# ---------------------------------------------------------------------------
# Zobrist hashing: keys seeded per-match from transition_matrix hash.
# Keys: one 64-bit value per (slot, cell) where slot ∈ {space, primed, carpet,
# blocked, us_worker, opp_worker}. Plus a side-to-move toggle and score bands.
# ---------------------------------------------------------------------------

_ZOBRIST_CACHE: dict[bytes, "ZobristKeys"] = {}


@dataclass(frozen=True)
class ZobristKeys:
    slot_cell: tuple[tuple[int, ...], ...]  # [6][64]
    us_worker: tuple[int, ...]              # [64]
    opp_worker: tuple[int, ...]             # [64]
    side_to_move: int
    # Score banding: score delta modulo 32.
    us_score_band: tuple[int, ...]
    opp_score_band: tuple[int, ...]


def zobrist_for_matrix(transition_matrix: np.ndarray) -> ZobristKeys:
    """Zobrist keys deterministic given the transition matrix (shared per match)."""
    t = np.asarray(transition_matrix, dtype=np.float64)
    key = hashlib.sha256(t.tobytes()).digest()[:16]
    cached = _ZOBRIST_CACHE.get(key)
    if cached is not None:
        return cached

    rng = random.Random(int.from_bytes(key, "big"))

    def rnd() -> int:
        return rng.getrandbits(64)

    slot_cell = tuple(tuple(rnd() for _ in range(NUM_CELLS)) for _ in range(6))
    us_worker = tuple(rnd() for _ in range(NUM_CELLS))
    opp_worker = tuple(rnd() for _ in range(NUM_CELLS))
    side = rnd()
    us_band = tuple(rnd() for _ in range(32))
    opp_band = tuple(rnd() for _ in range(32))
    keys = ZobristKeys(slot_cell, us_worker, opp_worker, side, us_band, opp_band)
    _ZOBRIST_CACHE[key] = keys
    return keys


# ---------------------------------------------------------------------------
# Encoded moves: a tiny int tuple representation for cache/TT friendliness.
# Encoding: (move_type, direction_or_search_idx, roll_length).
#   - PLAIN:  (0, dir, 0)
#   - PRIME:  (1, dir, 0)
#   - CARPET: (2, dir, roll_length)
#   - SEARCH: (3, search_idx, 0)    -- search moves are NOT expanded in the tree
# ---------------------------------------------------------------------------

MoveKey = Tuple[int, int, int]


def move_to_key(move: Move) -> MoveKey:
    mt = move.move_type
    if mt == MoveType.PLAIN:
        return (0, int(move.direction), 0)
    if mt == MoveType.PRIME:
        return (1, int(move.direction), 0)
    if mt == MoveType.CARPET:
        return (2, int(move.direction), int(move.roll_length))
    if mt == MoveType.SEARCH:
        if move.search_loc is None:
            return (3, 0, 0)
        x, y = move.search_loc
        return (3, coord_to_idx(x, y), 0)
    return (-1, 0, 0)


def key_to_move(key: MoveKey) -> Move:
    mt, a, b = key
    if mt == 0:
        return Move.plain(Direction(a))
    if mt == 1:
        return Move.prime(Direction(a))
    if mt == 2:
        return Move.carpet(Direction(a), b)
    if mt == 3:
        return Move.search(idx_to_coord(a))
    raise ValueError(f"invalid move key {key!r}")


def move_immediate_points(key: MoveKey) -> int:
    """Deterministic score delta a move adds to the mover's points *this turn*.

    PLAIN = 0, PRIME = +1, CARPET(k) = CARPET_POINTS_TABLE[k]. SEARCH is treated
    as 0 here (its EV is computed separately via belief peak). This matches the
    engine's `apply_move` scoring exactly and is the correct unit for the
    search-vs-move gate in `search_policy.decide_search`."""
    mt, _a, b = key
    if mt == 0:
        return 0
    if mt == 1:
        return 1
    if mt == 2:
        if 0 <= b < len(CARPET_POINTS_LUT):
            return int(CARPET_POINTS_LUT[b])
        return -10_000
    return 0


# ---------------------------------------------------------------------------
# State.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BBState:
    """Immutable bitboard representation of a mid-game state.

    All masks are 64-bit ints with bit (y*8 + x). Exactly one of
    {space, primed, carpet, blocked} is set per cell (modulo worker
    occupation, which is tracked separately)."""

    space: int
    primed: int
    carpet: int
    blocked: int
    us: int            # worker cell index 0..63
    opp: int           # worker cell index 0..63
    us_score: int
    opp_score: int
    us_turns: int
    opp_turns: int
    us_to_move: bool

    # ---------------- Utility ----------------
    @property
    def occupied(self) -> int:
        return (1 << self.us) | (1 << self.opp)

    @property
    def walkable(self) -> int:
        """Cells we may step onto (SPACE or CARPET), excluding workers/primed."""
        return (self.space | self.carpet) & ~self.occupied

    @property
    def plain_exits_from_me(self) -> int:
        return ADJ[self.us] & self.walkable

    def is_terminal(self) -> bool:
        return self.us_turns <= 0 and self.opp_turns <= 0

    def score_diff_us(self) -> int:
        """Score diff from our viewpoint — doesn't depend on side to move."""
        return self.us_score - self.opp_score

    # ---------------- Conversion from engine Board ----------------
    @staticmethod
    def from_board(board: Board) -> "BBState":
        """Build a BBState from the engine board. Convention: `us` = the side
        whose turn it is to move on this board (board.player_worker)."""
        blocked = int(board._blocked_mask) & FULL_MASK
        primed = int(board._primed_mask) & FULL_MASK
        carpet = int(board._carpet_mask) & FULL_MASK
        space = FULL_MASK & ~(blocked | primed | carpet)

        pw_loc = board.player_worker.get_location()
        ow_loc = board.opponent_worker.get_location()
        return BBState(
            space=space,
            primed=primed,
            carpet=carpet,
            blocked=blocked,
            us=coord_to_idx(pw_loc[0], pw_loc[1]),
            opp=coord_to_idx(ow_loc[0], ow_loc[1]),
            us_score=int(board.player_worker.get_points()),
            opp_score=int(board.opponent_worker.get_points()),
            us_turns=int(board.player_worker.turns_left),
            opp_turns=int(board.opponent_worker.turns_left),
            us_to_move=True,
        )


# ---------------------------------------------------------------------------
# Move generation.
# ---------------------------------------------------------------------------


def _plain_prime_targets(state: BBState, from_idx: int) -> int:
    """Cells the worker at from_idx can plain/prime-step into.

    Mirrors the engine: must be in-bounds (ADJ already enforces), not blocked,
    not primed, not occupied by the other worker."""
    off_limits = state.blocked | state.primed | (1 << state.opp) | (1 << state.us)
    return ADJ[from_idx] & ~off_limits


def generate_moves(state: BBState) -> list[MoveKey]:
    """Full list of non-search legal moves for the side to move.

    SEARCH is handled by `search_policy` at the root, not in the tree."""
    moves: list[MoveKey] = []
    if state.us_turns <= 0:
        return moves
    us_idx = state.us
    us_bit = 1 << us_idx
    plain_targets = _plain_prime_targets(state, us_idx)
    can_prime = not ((state.primed | state.carpet) & us_bit)

    for d in range(NUM_DIR):
        nb = NEIGHBOR[us_idx][d]
        if nb < 0:
            continue
        if plain_targets & (1 << nb):
            moves.append((0, d, 0))
            if can_prime:
                moves.append((1, d, 0))

        # CARPET along direction d — each cell must be primed and not occupied.
        opp_bit = 1 << state.opp
        cur = us_idx
        for k in range(1, BOARD_SIZE):
            cur = NEIGHBOR[cur][d]
            if cur < 0:
                break
            cell_bit = 1 << cur
            if not (state.primed & cell_bit):
                break
            if cell_bit & opp_bit:
                break
            moves.append((2, d, k))

    return moves


def count_mobility(state: BBState) -> int:
    """Cheap popcount of plain-step exits from the side-to-move worker."""
    return _popcount(_plain_prime_targets(state, state.us))


# ---------------------------------------------------------------------------
# Transitions.
# ---------------------------------------------------------------------------


def _swap_sides(state: BBState) -> BBState:
    """Swap perspective after a move: the old opponent becomes `us`."""
    return BBState(
        space=state.space,
        primed=state.primed,
        carpet=state.carpet,
        blocked=state.blocked,
        us=state.opp,
        opp=state.us,
        us_score=state.opp_score,
        opp_score=state.us_score,
        us_turns=state.opp_turns,
        opp_turns=state.us_turns - 1,  # we just consumed a turn
        us_to_move=not state.us_to_move,
    )


def apply_move_key(state: BBState, key: MoveKey) -> BBState:
    """Apply a non-search move and swap perspective. Does NOT validate; caller
    must have sourced the key from `generate_moves`."""
    mt, a, b = key
    us_idx = state.us
    space = state.space
    primed = state.primed
    carpet = state.carpet
    us_score = state.us_score
    opp_score = state.opp_score
    us_turns = state.us_turns

    if mt == 0:  # PLAIN
        nb = NEIGHBOR[us_idx][a]
        new_state = BBState(
            space=space,
            primed=primed,
            carpet=carpet,
            blocked=state.blocked,
            us=nb,
            opp=state.opp,
            us_score=us_score,
            opp_score=opp_score,
            us_turns=us_turns,
            opp_turns=state.opp_turns,
            us_to_move=state.us_to_move,
        )
        return _swap_sides(new_state)

    if mt == 1:  # PRIME
        nb = NEIGHBOR[us_idx][a]
        us_bit = 1 << us_idx
        new_space = space & ~us_bit
        new_primed = primed | us_bit
        new_state = BBState(
            space=new_space,
            primed=new_primed,
            carpet=carpet,
            blocked=state.blocked,
            us=nb,
            opp=state.opp,
            us_score=us_score + 1,
            opp_score=opp_score,
            us_turns=us_turns,
            opp_turns=state.opp_turns,
            us_to_move=state.us_to_move,
        )
        return _swap_sides(new_state)

    if mt == 2:  # CARPET
        # Walk roll_length cells along direction a; convert each primed → carpet.
        new_primed = primed
        new_carpet = carpet
        cur = us_idx
        final = us_idx
        for _ in range(b):
            cur = NEIGHBOR[cur][a]
            cell_bit = 1 << cur
            new_primed &= ~cell_bit
            new_carpet |= cell_bit
            final = cur
        points = CARPET_POINTS_LUT[b] if 0 <= b < len(CARPET_POINTS_LUT) else -10_000
        new_state = BBState(
            space=space,
            primed=new_primed,
            carpet=new_carpet,
            blocked=state.blocked,
            us=final,
            opp=state.opp,
            us_score=us_score + points,
            opp_score=opp_score,
            us_turns=us_turns,
            opp_turns=state.opp_turns,
            us_to_move=state.us_to_move,
        )
        return _swap_sides(new_state)

    raise ValueError(f"unsupported move type in apply_move_key: {mt}")


# ---------------------------------------------------------------------------
# Zobrist hashing for a state.
# ---------------------------------------------------------------------------


def zobrist_hash(state: BBState, keys: ZobristKeys) -> int:
    """Hash every cell's slot + worker positions + side-to-move + score bands."""
    h = 0
    # Slot layout: 0 space, 1 primed, 2 carpet, 3 blocked.
    for slot_id, mask in (
        (0, state.space),
        (1, state.primed),
        (2, state.carpet),
        (3, state.blocked),
    ):
        row = keys.slot_cell[slot_id]
        m = mask
        while m:
            lsb = m & -m
            idx = lsb.bit_length() - 1
            h ^= row[idx]
            m &= m - 1
    h ^= keys.us_worker[state.us]
    h ^= keys.opp_worker[state.opp]
    if state.us_to_move:
        h ^= keys.side_to_move
    h ^= keys.us_score_band[state.us_score % 32]
    h ^= keys.opp_score_band[state.opp_score % 32]
    return h & 0xFFFFFFFFFFFFFFFF

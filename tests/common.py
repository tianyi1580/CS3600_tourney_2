from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = ROOT / "engine"
AGENTS_DIR = ROOT / "3600-agents"

if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

from game.board import Board  # noqa: E402


def identity_transition() -> np.ndarray:
    return np.eye(64, dtype=np.float64)


def random_stochastic_transition(
    rng: np.random.Generator | None = None,
    dim: int = 64,
) -> np.ndarray:
    """Row-stochastic matrix for belief tests (BeliefEngine re-normalizes rows defensively)."""
    if rng is None:
        rng = np.random.default_rng(0)
    m = rng.random((dim, dim), dtype=np.float64)
    m /= m.sum(axis=1, keepdims=True)
    return m


def make_board(time_to_play: float = 240.0) -> Board:
    b = Board(time_to_play=time_to_play)
    b.player_worker.position = (3, 3)
    b.opponent_worker.position = (4, 4)
    return b

"""Information-gain foraging: bias worker movement toward sensor-rich cells.

For each candidate *worker position* (after a PLAIN or PRIME step), compute the
expected posterior entropy under the noise + distance sensor model, given the
current belief. Large reductions in expected entropy get rewarded as an
`epsilon · belief_info_bonus` term inside the leaf evaluator.

Gated on `H_norm > info_entropy_gate` so this only kicks in when we are
genuinely uncertain about the rat. Late-game cashouts should not be hijacked
by speculative positional information play."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from game.enums import BOARD_SIZE
from game.rat import DISTANCE_ERROR_OFFSETS, DISTANCE_ERROR_PROBS

from ..infra.bitboard import BBState, L1, NUM_CELLS


_MAX_DIST = 2 * (BOARD_SIZE - 1)
_MAX_REPORTED = _MAX_DIST + max(DISTANCE_ERROR_OFFSETS)  # 16
_LOG_N = math.log(NUM_CELLS)


def _build_dist_lut() -> np.ndarray:
    """dist_lut[actual_dist, reported] — P(reported | actual)."""
    lut = np.zeros((_MAX_DIST + 1, _MAX_REPORTED + 1), dtype=np.float64)
    for d in range(_MAX_DIST + 1):
        for offset, prob in zip(DISTANCE_ERROR_OFFSETS, DISTANCE_ERROR_PROBS):
            r = max(0, d + offset)
            if r <= _MAX_REPORTED:
                lut[d, r] += prob
    return lut


_DIST_LUT = _build_dist_lut()


@dataclass(slots=True)
class InfoForagingContext:
    """Per-turn context for information foraging.

    We cache the belief, the cell-type noise distribution, and the normalized
    entropy so the leaf evaluator can produce O(64)-time info bonuses without
    recomputing the expensive probabilities."""

    belief: np.ndarray             # (64,)
    cell_noise_marginal: np.ndarray  # (64,) prior prob of noise-type observed elsewhere — unused
    noise_cond: np.ndarray         # (64, 3) P(noise | rat = cell) for each of 3 noise labels.
    entropy_norm: float
    gate_threshold: float = 0.75

    def is_active(self) -> bool:
        return self.entropy_norm > self.gate_threshold


def build_context(
    belief: np.ndarray,
    noise_lut: np.ndarray,
    cell_types: np.ndarray,
    gate_threshold: float = 0.75,
) -> InfoForagingContext:
    """Build a per-turn foraging context from the current belief + board cell types."""
    p = np.maximum(belief, 1e-12)
    ent = float(-np.sum(p * np.log(p)))
    ent_norm = ent / _LOG_N

    # noise_cond[c, n] = P(noise = n | rat = c) — independent of worker pos.
    noise_cond = noise_lut[cell_types]  # shape (64, 3)
    # Marginal over cells isn't needed; the belief weighs by rat prior.
    cell_noise_marginal = np.zeros(NUM_CELLS, dtype=np.float64)

    return InfoForagingContext(
        belief=belief,
        cell_noise_marginal=cell_noise_marginal,
        noise_cond=noise_cond,
        entropy_norm=ent_norm,
        gate_threshold=float(gate_threshold),
    )


def expected_entropy_reduction(
    worker_idx: int,
    ctx: InfoForagingContext,
) -> float:
    """Entropy drop (in nats) we *expect* to see after taking a sensor reading
    from `worker_idx`. Positive = sensor is informative from this position.

    Full enumeration:
      E[H_post] = Σ_obs P(obs | belief) · H(posterior(obs))

    Uses numpy vectorization over the 64 × 3 × len(reported) table."""
    belief = ctx.belief
    noise_cond = ctx.noise_cond
    actual_dists = L1[worker_idx]  # (64,)
    dist_probs = _DIST_LUT[actual_dists]  # (64, MAX_REPORTED + 1)

    # Joint P(obs | rat = cell) = noise_cond[c, n] * dist_probs[c, r]
    # Shape: (64, 3, R)
    joint = noise_cond[:, :, None] * dist_probs[:, None, :]
    # Weight by belief prior.
    weighted = belief[:, None, None] * joint  # shape (64, 3, R)

    # P(obs) = Σ_c weighted[c, n, r]  -> shape (3, R)
    p_obs = weighted.sum(axis=0)

    # Posterior: p_post[c, n, r] = weighted / p_obs  where p_obs > 0
    eps = 1e-12
    norm = np.where(p_obs > eps, p_obs, 1.0)
    posterior = weighted / norm[None, :, :]  # (64, 3, R)

    # Entropy of each posterior: H[n, r] = -Σ_c posterior[c, n, r] log posterior[c, n, r]
    safe_post = np.maximum(posterior, eps)
    H_obs = -(posterior * np.log(safe_post)).sum(axis=0)  # (3, R)

    # Expected posterior entropy.
    exp_H = float((p_obs * H_obs).sum())

    H_prior = float(-np.sum(np.where(belief > eps, belief * np.log(np.maximum(belief, eps)), 0.0)))
    return max(0.0, H_prior - exp_H)


def build_belief_info_fn(ctx: Optional[InfoForagingContext]):
    """Factory: return a callable `f(state) -> bonus` bound to this context.

    If ctx is inactive (low entropy), returns a no-op."""
    if ctx is None or not ctx.is_active():
        return lambda state: 0.0

    cache: dict[int, float] = {}

    def _fn(state: BBState) -> float:
        wi = state.us
        v = cache.get(wi)
        if v is None:
            v = expected_entropy_reduction(wi, ctx)
            cache[wi] = v
        return v

    return _fn

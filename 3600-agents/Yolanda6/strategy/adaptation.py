"""
Bounded opponent adaptation utilities.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..tracking.opponent_observation import OpponentCategory

OPPONENT_WINDOW = 24

BASE_A = 1.00
BASE_B = 0.45
BASE_C = 0.60
BASE_D = 0.35
BASE_E = 1.00
BASE_F = 0.75

D_CLAMP_A = (-0.10, 0.10)
D_CLAMP_C = (-0.10, 0.10)
D_CLAMP_D = (-0.15, 0.15)
D_CLAMP_F = (-0.10, 0.10)

ENV_A = (0.80, 1.20)
ENV_C = (0.45, 0.75)
ENV_D = (0.20, 0.55)
ENV_F = (0.55, 0.95)

CONFIDENCE_FLOOR = 0.35
MIN_OBSERVED_TURNS = 6


@dataclass
class RawDeltas:
    da: float = 0.0
    dc: float = 0.0
    dd: float = 0.0
    df: float = 0.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def normalized_entropy_category_counts(counts: dict[OpponentCategory, int]) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        if c <= 0:
            continue
        p = c / total
        h -= p * math.log(p + 1e-15)
    return h / math.log(4.0)


def compute_confidence(observed_turns: int, behavior_entropy_norm: float) -> float:
    t = _clamp((observed_turns - 5) / 10.0, 0.0, 1.0)
    return t * (1.0 - _clamp(behavior_entropy_norm, 0.0, 1.0))


def pattern_raw_deltas(
    *,
    category_hist: dict[OpponentCategory, int],
    total_typed: int,
    mean_opp_mobility: float,
    low_exit_rate: float,
    search_attempts: int,
    search_correct: int,
) -> RawDeltas:
    r = RawDeltas()
    if total_typed <= 0:
        return r

    prime_frac = category_hist.get(OpponentCategory.PRIME, 0) / total_typed
    carpet_frac = category_hist.get(OpponentCategory.CARPET, 0) / total_typed
    search_frac = category_hist.get(OpponentCategory.SEARCH, 0) / total_typed

    if low_exit_rate >= 0.40 and total_typed >= 8:
        r.dd += 0.15
    if search_attempts >= 4:
        acc = search_correct / max(1, search_attempts)
        if acc < 0.25:
            r.da += 0.10
    if total_typed >= 8 and mean_opp_mobility <= 2.25:
        r.dc += 0.10
    if prime_frac >= 0.38 or (
        prime_frac >= 0.30 and prime_frac >= carpet_frac + 0.1 and prime_frac >= search_frac + 0.1
    ):
        r.df += 0.10

    return r


def apply_adaptation(
    confidence: float,
    raw: RawDeltas,
    base_a: float = BASE_A,
    base_c: float = BASE_C,
    base_d: float = BASE_D,
    base_f: float = BASE_F,
) -> tuple[float, float, float, float]:
    if confidence < CONFIDENCE_FLOOR:
        return base_a, base_c, base_d, base_f

    da = _clamp(confidence * raw.da, D_CLAMP_A[0], D_CLAMP_A[1])
    dc = _clamp(confidence * raw.dc, D_CLAMP_C[0], D_CLAMP_C[1])
    dd = _clamp(confidence * raw.dd, D_CLAMP_D[0], D_CLAMP_D[1])
    df = _clamp(confidence * raw.df, D_CLAMP_F[0], D_CLAMP_F[1])

    a = _clamp(base_a + da, ENV_A[0], ENV_A[1])
    c = _clamp(base_c + dc, ENV_C[0], ENV_C[1])
    d = _clamp(base_d + dd, ENV_D[0], ENV_D[1])
    f = _clamp(base_f + df, ENV_F[0], ENV_F[1])
    return a, c, d, f

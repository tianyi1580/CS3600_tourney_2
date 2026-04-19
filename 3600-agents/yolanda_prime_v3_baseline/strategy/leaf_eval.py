"""Five-term leaf evaluator for the alpha-beta search.

All values are *returned in the side-to-move frame* (positive = side to move is
winning). The search uses negamax and negates across plies, so we return
`sign(us_to_move) * raw_diff` — but simpler: we directly compute from the
state's `us`/`opp` fields, since after a perspective swap the new `us` is the
side about to move."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from ..infra.bitboard import (
    BBState,
    MoveKey,
    NUM_CELLS,
    count_mobility,
)
from .territory import fast_territory_delta, worker_chain_potential


@dataclass(slots=True)
class LeafEvalConfig:
    alpha: float = 1.0
    beta: float = 0.35
    gamma: float = 0.25
    delta: float = 0.05
    epsilon: float = 0.12
    omega_threat: float = 0.60


class LeafEvaluator:
    """Stateful leaf evaluator bound to a prime-potential field + belief info.

    `prime_pot_field` is computed once per turn at the root and shared across
    all tree nodes. `belief_info_fn` receives a `BBState` and returns a scalar
    info bonus — typically 0 outside high-entropy gates."""

    __slots__ = (
        "cfg",
        "prime_pot_field",
        "belief_info_fn",
        "_calls",
    )

    def __init__(
        self,
        cfg: LeafEvalConfig,
        prime_pot_field: np.ndarray,
        belief_info_fn: Optional[Callable[[BBState], float]] = None,
    ):
        self.cfg = cfg
        self.prime_pot_field = prime_pot_field
        self.belief_info_fn = belief_info_fn
        self._calls = 0

    def __call__(self, state: BBState) -> float:
        return self.evaluate(state)

    def evaluate(self, state: BBState) -> float:
        self._calls += 1
        cfg = self.cfg

        score_delta = float(state.us_score - state.opp_score)

        territory_d = fast_territory_delta(state, self.prime_pot_field)

        us_chain = worker_chain_potential(state, for_us=True)
        opp_chain = worker_chain_potential(state, for_us=False)
        chain_d = float(us_chain - opp_chain)

        mob_us = count_mobility(state)
        # Cheap opp mobility: swap perspective briefly via L1-adjacent walkable
        # count. Build it manually to avoid allocating a full BBState.
        mob_opp = _count_opponent_mobility(state)
        mob_d = float(mob_us - mob_opp)

        info_bonus = 0.0
        if self.belief_info_fn is not None:
            info_bonus = float(self.belief_info_fn(state))

        threat_pen = 0.0
        # Threat penalty: if after our move the opponent can answer with a
        # carpet of yield >= 6 and we don't have a matching reply, penalize.
        if opp_chain >= 6 and us_chain < opp_chain:
            threat_pen = float(opp_chain - us_chain)

        return (
            cfg.alpha * score_delta
            + cfg.beta * territory_d
            + cfg.gamma * chain_d
            + cfg.delta * mob_d
            + cfg.epsilon * info_bonus
            - cfg.omega_threat * threat_pen
        )

    def stats(self) -> dict:
        return {"calls": self._calls}


def _count_opponent_mobility(state: BBState) -> int:
    from ..infra.bitboard import ADJ, _popcount  # noqa

    blocked = state.blocked | state.primed | (1 << state.us) | (1 << state.opp)
    targets = ADJ[state.opp] & ~blocked
    return bin(targets & ((1 << NUM_CELLS) - 1)).count("1")


def build_leaf_eval(
    weights: dict,
    prime_pot_field: np.ndarray,
    belief_info_fn: Optional[Callable[[BBState], float]] = None,
) -> LeafEvaluator:
    cfg = LeafEvalConfig(
        alpha=float(weights.get("alpha", 1.0)),
        beta=float(weights.get("beta", 0.35)),
        gamma=float(weights.get("gamma", 0.25)),
        delta=float(weights.get("delta", 0.05)),
        epsilon=float(weights.get("epsilon", 0.12)),
        omega_threat=float(weights.get("omega_threat", 0.6)),
    )
    return LeafEvaluator(cfg=cfg, prime_pot_field=prime_pot_field, belief_info_fn=belief_info_fn)

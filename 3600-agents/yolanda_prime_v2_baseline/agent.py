from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from yolanda_prime_v2.agent import ConfiguredPlayerAgent


class PlayerAgent(ConfiguredPlayerAgent):
    """Frozen-weight control for hyperopt: package ``weights.json`` unless
    ``YP2_BASELINE_WEIGHTS_JSON`` is set.

    Uses a separate env channel from the tunable candidate
    (``yolanda_prime_v2`` / ``YP2_WEIGHTS_JSON``) so ladder games against this
    opponent always evaluate the baseline weight snapshot, not the candidate
    vector.
    """

    def __init__(self, board, transition_matrix=None, time_left: Callable = None):
        baseline_root = Path(__file__).resolve().parent
        shared_code_root = Path(__file__).resolve().parents[1] / "yolanda_prime_v2"
        super().__init__(
            board,
            transition_matrix,
            time_left,
            weight_env_var="YP2_BASELINE_WEIGHTS_JSON",
            weights_root=baseline_root,
            allow_env_weights=True,
            commentate_name="yolanda_prime_v2_baseline",
            fingerprint_root=shared_code_root,
        )

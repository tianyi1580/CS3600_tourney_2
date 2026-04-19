from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from yolanda_prime_v1_2.agent import ConfiguredPlayerAgent


class PlayerAgent(ConfiguredPlayerAgent):
    """Frozen-weight control wrapper used for candidate-vs-baseline tuning."""

    def __init__(self, board, transition_matrix=None, time_left: Callable = None):
        baseline_root = Path(__file__).resolve().parent
        shared_code_root = Path(__file__).resolve().parents[1] / "yolanda_prime_v1_2"
        super().__init__(
            board,
            transition_matrix,
            time_left,
            weight_env_var="YP12_BASELINE_WEIGHTS_JSON",
            weights_root=baseline_root,
            allow_env_weights=True,
            commentate_name="yolanda_prime_v1_2_baseline",
            fingerprint_root=shared_code_root,
        )

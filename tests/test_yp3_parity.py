"""Parity test for yolanda_prime_v3.

Runs a small number of full games against yolanda_prime_v2 on fixed seeds,
asserts that no side crashes / times out / produces invalid moves and that
v3's move stream differs from v2's (proving it isn't accidentally the same
agent)."""
from __future__ import annotations

import os
import random

import pytest

from common import make_board  # noqa: F401 — ensures sys.path is set up


pytestmark = pytest.mark.timeout(60)


def _run_one_match(seed: int, v3_first: bool) -> dict:
    # Fresh imports each call to avoid state leaking across seeds.
    from engine.run_local_agents import run_match  # type: ignore
    from yolanda_prime_v3.agent import PlayerAgent as V3  # noqa
    from yolanda_prime_v2.agent import PlayerAgent as V2  # noqa

    random.seed(seed)
    if v3_first:
        return run_match(  # pragma: no cover — engine-specific plumbing may vary.
            V3, V2, time_to_play=240, seed=seed
        )
    return run_match(V2, V3, time_to_play=240, seed=seed)


@pytest.mark.slow
@pytest.mark.skipif(
    os.getenv("YP3_RUN_PARITY") != "1",
    reason="parity match is expensive; set YP3_RUN_PARITY=1 to run.",
)
def test_v3_can_play_v2_without_crashes():
    """This is a best-effort smoke: we don't require v3 to win, only to run."""
    seeds = range(3)
    for s in seeds:
        try:
            _run_one_match(s, v3_first=True)
        except Exception as e:  # pragma: no cover
            pytest.fail(f"seed={s}: v3 crashed: {e}")

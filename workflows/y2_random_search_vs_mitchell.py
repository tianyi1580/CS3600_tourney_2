#!/usr/bin/env python3
from __future__ import annotations

import argparse
import random
from dataclasses import dataclass

from y2_tune_vs_mitchell import DEFAULTS, run_series


@dataclass
class EvalResult:
    cfg: dict[str, str]
    mean_delta: float
    win_rate: float
    wins: int
    losses: int
    games: int


def score_tuple(r: EvalResult) -> tuple[float, float, int]:
    return (r.mean_delta, r.win_rate, -r.losses)


def evaluate_cfg(cfg: dict[str, str], *, seeds: list[int], games_per_seed: int, opponent: str) -> EvalResult:
    total_w = total_l = total_games = 0
    weighted_delta = 0.0
    weighted_wr = 0.0
    for s in seeds:
        res = run_series(cfg, games=games_per_seed, seed_start=s, opponent=opponent)
        g = int(res["games"])
        total_games += g
        total_w += int(res["wins"])
        total_l += int(res["losses"])
        weighted_delta += float(res["mean_delta"]) * g
        weighted_wr += float(res["win_rate"]) * g
    mean_delta = weighted_delta / total_games if total_games else 0.0
    win_rate = weighted_wr / total_games if total_games else 0.0
    return EvalResult(cfg=cfg, mean_delta=mean_delta, win_rate=win_rate, wins=total_w, losses=total_l, games=total_games)


def sample_cfg(rng: random.Random) -> dict[str, str]:
    cfg = dict(DEFAULTS)

    cfg["Y2_ENABLE_LEAD_AWARE_CENTRALITY"] = rng.choice(["0", "1"])
    cfg["Y2_MID_LEAD_CENTRALITY_SCALE"] = str(rng.choice([0.0, 0.15, 0.3, 0.5, 0.7]))
    cfg["Y2_MID_LEAD_SPACE_BONUS"] = str(rng.choice([0.0, 0.25, 0.5, 0.75]))
    cfg["Y2_MID_TRAILING_CENTRALITY_SCALE"] = str(rng.choice([0.8, 1.0, 1.2]))

    cfg["Y2_ENABLE_SABOTAGE"] = rng.choice(["0", "1"])
    cfg["Y2_SABOTAGE_BONUS"] = str(rng.choice([0.0, 1.0, 2.0, 2.5, 3.0, 4.0]))
    cfg["Y2_SABOTAGE_OPP_DIST"] = str(rng.choice([1, 2, 3]))
    cfg["Y2_SABOTAGE_MIN_CHAIN_LEN"] = str(rng.choice([3, 4]))

    cfg["Y2_ENABLE_FAST_SEARCH"] = rng.choice(["0", "1"])
    cfg["Y2_FAST_SEARCH_PROB"] = str(rng.choice([0.75, 0.80, 0.85, 0.90, 0.93]))
    cfg["Y2_FAST_SEARCH_MAX_CARPET"] = str(rng.choice([8.0, 10.0, 12.0, 15.0]))

    cfg["Y2_ENABLE_THREATENED_CASHOUT"] = rng.choice(["0", "1"])
    cfg["Y2_THREAT_CASHOUT_BONUS"] = str(rng.choice([0.0, 2.0, 4.0, 6.0]))
    cfg["Y2_THREAT_CASHOUT_MIN_ROLL"] = str(rng.choice([3, 4, 5]))
    cfg["Y2_THREAT_CASHOUT_OPP_DIST"] = str(rng.choice([1, 2, 3]))

    cfg["Y2_ENABLE_OPENING_LONG_CARPET"] = rng.choice(["0", "1"])
    cfg["Y2_OPENING_KEEP_MIN_ROLL"] = str(rng.choice([4, 5, 6, 7]))

    return cfg


def print_eval(prefix: str, res: EvalResult, default_cfg: dict[str, str]) -> None:
    changed = {k: v for k, v in res.cfg.items() if default_cfg.get(k) != v}
    print(
        f"{prefix} delta={res.mean_delta:+.3f} win_rate={res.win_rate:.3f} "
        f"wins={res.wins} losses={res.losses} games={res.games} changed={len(changed)}"
    )
    if changed:
        print("  " + ", ".join(f"{k}={v}" for k, v in sorted(changed.items())))


def main() -> int:
    p = argparse.ArgumentParser(description="Random-search Yolanda2 knobs vs yolanda_mitchell")
    p.add_argument("--samples", type=int, default=24)
    p.add_argument("--quick-games", type=int, default=10)
    p.add_argument("--quick-seeds", type=int, default=2)
    p.add_argument("--refine-topk", type=int, default=5)
    p.add_argument("--refine-games", type=int, default=20)
    p.add_argument("--refine-seeds", type=int, default=3)
    p.add_argument("--seed", type=int, default=1337)
    p.add_argument("--opponent", default="yolanda_mitchell")
    args = p.parse_args()

    rng = random.Random(args.seed)

    quick_seed_list = [4000 + 100 * i for i in range(args.quick_seeds)]
    refine_seed_list = [8000 + 100 * i for i in range(args.refine_seeds)]

    print("=== Baseline (default Yolanda2) ===")
    baseline = evaluate_cfg({}, seeds=quick_seed_list, games_per_seed=args.quick_games, opponent=args.opponent)
    print_eval("baseline.quick", baseline, DEFAULTS)

    candidates: list[EvalResult] = []
    for i in range(args.samples):
        cfg = sample_cfg(rng)
        res = evaluate_cfg(cfg, seeds=quick_seed_list, games_per_seed=args.quick_games, opponent=args.opponent)
        candidates.append(res)
        print_eval(f"sample#{i+1:02d}.quick", res, DEFAULTS)

    candidates.sort(key=score_tuple, reverse=True)
    top = candidates[: max(1, args.refine_topk)]

    print("\n=== Refinement on top candidates ===")
    refined: list[EvalResult] = []
    for i, c in enumerate(top, 1):
        rr = evaluate_cfg(c.cfg, seeds=refine_seed_list, games_per_seed=args.refine_games, opponent=args.opponent)
        refined.append(rr)
        print_eval(f"top#{i:02d}.refine", rr, DEFAULTS)

    refined.sort(key=score_tuple, reverse=True)
    best = refined[0]

    print("\n=== Best Config ===")
    print_eval("best", best, DEFAULTS)
    print("\nRecommended overrides:")
    changed = {k: v for k, v in best.cfg.items() if DEFAULTS.get(k) != v}
    if not changed:
        print("(none)")
    else:
        for k, v in sorted(changed.items()):
            print(f"{k}={v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

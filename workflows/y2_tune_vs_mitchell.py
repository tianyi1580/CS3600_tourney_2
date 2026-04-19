#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import io
import os
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = ROOT / "engine"
AGENTS_DIR = ROOT / "3600-agents"

if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

from gameplay import play_game
from game.enums import ResultArbiter

PLAY_DIR = str(AGENTS_DIR)

# All tunable knobs exposed by Yolanda2.agent -> PolicyEngine.
DEFAULTS: dict[str, str] = {
    "Y2_ENABLE_LEAD_AWARE_CENTRALITY": "1",
    "Y2_MID_LEAD_CENTRALITY_SCALE": "0.3",
    "Y2_MID_TRAILING_CENTRALITY_SCALE": "1.0",
    "Y2_OPENING_CENTRALITY_SCALE": "1.5",
    "Y2_LATE_CENTRALITY_SCALE": "0.3",
    "Y2_MID_LEAD_SPACE_BONUS": "0.5",
    "Y2_ENABLE_THREATENED_CASHOUT": "1",
    "Y2_THREAT_CASHOUT_MIN_ROLL": "4",
    "Y2_THREAT_CASHOUT_OPP_DIST": "2",
    "Y2_THREAT_CASHOUT_BONUS": "4.0",
    "Y2_ENABLE_SABOTAGE": "1",
    "Y2_SABOTAGE_MIN_CHAIN_LEN": "3",
    "Y2_SABOTAGE_OPP_DIST": "2",
    "Y2_SABOTAGE_BONUS": "2.5",
    "Y2_ENABLE_FAST_SEARCH": "1",
    "Y2_FAST_SEARCH_PROB": "0.85",
    "Y2_FAST_SEARCH_MAX_CARPET": "10.0",
    "Y2_ENABLE_OPENING_LONG_CARPET": "1",
    "Y2_OPENING_KEEP_MIN_ROLL": "5",
}

Y2_KEYS = sorted(DEFAULTS.keys())


def _absolute_ab_scores(board) -> tuple[int, int]:
    if board.player_worker.is_player_a:
        return board.player_worker.get_points(), board.opponent_worker.get_points()
    return board.opponent_worker.get_points(), board.player_worker.get_points()


@contextlib.contextmanager
def apply_y2_env(overrides: dict[str, str]):
    backup = {k: os.environ.get(k) for k in Y2_KEYS}
    try:
        for k in Y2_KEYS:
            v = overrides.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        yield
    finally:
        for k, v in backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def run_series(
    y2_overrides: dict[str, str],
    *,
    games: int,
    seed_start: int,
    opponent: str = "yolanda_mitchell",
) -> dict[str, float | int]:
    env_cfg = dict(DEFAULTS)
    env_cfg.update(y2_overrides)

    wins = losses = ties = 0
    deltas: list[float] = []

    with apply_y2_env(env_cfg):
        for g in range(games):
            random.seed(seed_start + g)
            y2_is_a = (g % 2 == 0)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                if y2_is_a:
                    board, *_ = play_game(
                        PLAY_DIR,
                        PLAY_DIR,
                        "Yolanda2",
                        opponent,
                        display_game=False,
                        delay=0,
                        clear_screen=False,
                        record=False,
                        limit_resources=False,
                        play_time_override=360,
                    )
                    sa, sb = _absolute_ab_scores(board)
                    y2_score, opp_score = sa, sb
                    winner = board.winner
                    y2_won = winner == ResultArbiter.PLAYER_A
                    y2_lost = winner == ResultArbiter.PLAYER_B
                else:
                    board, *_ = play_game(
                        PLAY_DIR,
                        PLAY_DIR,
                        opponent,
                        "Yolanda2",
                        display_game=False,
                        delay=0,
                        clear_screen=False,
                        record=False,
                        limit_resources=False,
                        play_time_override=360,
                    )
                    sa, sb = _absolute_ab_scores(board)
                    y2_score, opp_score = sb, sa
                    winner = board.winner
                    y2_won = winner == ResultArbiter.PLAYER_B
                    y2_lost = winner == ResultArbiter.PLAYER_A

            deltas.append(float(y2_score - opp_score))
            if y2_won:
                wins += 1
            elif y2_lost:
                losses += 1
            else:
                ties += 1

    mean_delta = statistics.fmean(deltas) if deltas else 0.0
    win_rate = wins / games if games else 0.0
    return {
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "games": games,
        "mean_delta": mean_delta,
        "win_rate": win_rate,
    }


def _score(res: dict[str, float | int]) -> tuple[float, float, int]:
    # Primary objective: positive score delta. Secondary: higher win rate and fewer losses.
    return (float(res["mean_delta"]), float(res["win_rate"]), -int(res["losses"]))


def _print_result(prefix: str, cfg: dict[str, str], res: dict[str, float | int]) -> None:
    print(
        f"{prefix} wins={res['wins']:>2} losses={res['losses']:>2} ties={res['ties']:>2} "
        f"mean_delta={res['mean_delta']:+.3f} win_rate={res['win_rate']:.3f}"
    )
    if cfg:
        print("  overrides:", ", ".join(f"{k}={v}" for k, v in sorted(cfg.items())))


def pick_best(
    base_cfg: dict[str, str],
    variants: list[dict[str, str]],
    *,
    games: int,
    seed_start: int,
    opponent: str,
    label: str,
) -> tuple[dict[str, str], dict[str, float | int]]:
    best_cfg = dict(base_cfg)
    best_res = run_series(best_cfg, games=games, seed_start=seed_start, opponent=opponent)
    _print_result(f"[{label}] baseline", {}, best_res)

    for i, patch in enumerate(variants, 1):
        cand = dict(base_cfg)
        cand.update(patch)
        res = run_series(cand, games=games, seed_start=seed_start, opponent=opponent)
        _print_result(f"[{label}] cand#{i:02d}", patch, res)
        if _score(res) > _score(best_res):
            best_cfg, best_res = cand, res

    print(f"[{label}] selected:\n")
    _print_result(f"[{label}] best", {k: v for k, v in best_cfg.items() if DEFAULTS.get(k) != v}, best_res)
    return best_cfg, best_res


def run_full(args: argparse.Namespace) -> int:
    print("=== Yolanda2 ablation vs yolanda_mitchell ===")
    baseline = run_series({}, games=args.ablation_games, seed_start=args.seed_start, opponent=args.opponent)
    _print_result("[ablation] baseline_all_on", {}, baseline)

    ablations = [
        ("lead_aware_centrality", {"Y2_ENABLE_LEAD_AWARE_CENTRALITY": "0"}),
        ("threatened_cashout", {"Y2_ENABLE_THREATENED_CASHOUT": "0"}),
        ("sabotage", {"Y2_ENABLE_SABOTAGE": "0"}),
        ("fast_search", {"Y2_ENABLE_FAST_SEARCH": "0"}),
        ("opening_long_carpet", {"Y2_ENABLE_OPENING_LONG_CARPET": "0"}),
    ]

    cfg = dict(DEFAULTS)
    for name, patch in ablations:
        res = run_series(patch, games=args.ablation_games, seed_start=args.seed_start, opponent=args.opponent)
        _print_result(f"[ablation] disable_{name}", patch, res)
        # Only keep disable if it strictly beats baseline on our primary metric.
        if _score(res) > _score(baseline):
            cfg.update(patch)
            baseline = res

    print("\n=== Stage 1: centrality tuning ===")
    centrality_variants = [
        {"Y2_MID_LEAD_CENTRALITY_SCALE": str(cs), "Y2_MID_LEAD_SPACE_BONUS": str(sb)}
        for cs in (0.0, 0.15, 0.3, 0.5)
        for sb in (0.0, 0.25, 0.5)
    ]
    cfg, _ = pick_best(
        cfg,
        centrality_variants,
        games=args.tune_games,
        seed_start=args.seed_start + 1000,
        opponent=args.opponent,
        label="centrality",
    )

    print("\n=== Stage 2: sabotage tuning ===")
    sabotage_variants = [
        {
            "Y2_SABOTAGE_BONUS": str(b),
            "Y2_SABOTAGE_OPP_DIST": str(d),
        }
        for b in (1.0, 2.0, 2.5, 3.0)
        for d in (1, 2, 3)
    ]
    cfg, _ = pick_best(
        cfg,
        sabotage_variants,
        games=args.tune_games,
        seed_start=args.seed_start + 2000,
        opponent=args.opponent,
        label="sabotage",
    )

    print("\n=== Stage 3: fast-search tuning ===")
    fast_variants = [
        {
            "Y2_FAST_SEARCH_PROB": str(p),
            "Y2_FAST_SEARCH_MAX_CARPET": str(mc),
        }
        for p in (0.80, 0.85, 0.90, 0.93)
        for mc in (8.0, 10.0, 12.0)
    ]
    cfg, _ = pick_best(
        cfg,
        fast_variants,
        games=args.tune_games,
        seed_start=args.seed_start + 3000,
        opponent=args.opponent,
        label="fast_search",
    )

    print("\n=== Stage 4: threatened cashout tuning ===")
    cashout_variants = [
        {
            "Y2_THREAT_CASHOUT_BONUS": str(b),
            "Y2_THREAT_CASHOUT_MIN_ROLL": str(k),
        }
        for b in (2.0, 4.0, 6.0)
        for k in (3, 4, 5)
    ]
    cfg, _ = pick_best(
        cfg,
        cashout_variants,
        games=args.tune_games,
        seed_start=args.seed_start + 4000,
        opponent=args.opponent,
        label="cashout",
    )

    print("\n=== Stage 5: opening exception tuning ===")
    opening_variants = [{"Y2_OPENING_KEEP_MIN_ROLL": str(k)} for k in (4, 5, 6, 7)]
    cfg, _ = pick_best(
        cfg,
        opening_variants,
        games=args.tune_games,
        seed_start=args.seed_start + 5000,
        opponent=args.opponent,
        label="opening",
    )

    print("\n=== Final validation vs primary target ===")
    final_vs_target = run_series(
        {k: v for k, v in cfg.items() if DEFAULTS.get(k) != v},
        games=args.final_games,
        seed_start=args.seed_start + 8000,
        opponent=args.opponent,
    )
    _print_result("[final] vs_primary", {k: v for k, v in cfg.items() if DEFAULTS.get(k) != v}, final_vs_target)

    print("\n=== Sanity validations ===")
    final_vs_y1 = run_series(
        {k: v for k, v in cfg.items() if DEFAULTS.get(k) != v},
        games=max(20, args.final_games // 2),
        seed_start=args.seed_start + 9000,
        opponent="Yolanda1",
    )
    _print_result("[final] vs_Yolanda1", {k: v for k, v in cfg.items() if DEFAULTS.get(k) != v}, final_vs_y1)

    final_vs_y = run_series(
        {k: v for k, v in cfg.items() if DEFAULTS.get(k) != v},
        games=max(20, args.final_games // 2),
        seed_start=args.seed_start + 10000,
        opponent="Yolanda",
    )
    _print_result("[final] vs_Yolanda", {k: v for k, v in cfg.items() if DEFAULTS.get(k) != v}, final_vs_y)

    print("\n=== Recommended env overrides ===")
    changed = {k: v for k, v in cfg.items() if DEFAULTS.get(k) != v}
    if not changed:
        print("(none)")
    else:
        for k, v in sorted(changed.items()):
            print(f"{k}={v}")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ablate and tune Yolanda2 against yolanda_mitchell")
    p.add_argument("--opponent", default="yolanda_mitchell")
    p.add_argument("--ablation-games", type=int, default=24)
    p.add_argument("--tune-games", type=int, default=10)
    p.add_argument("--final-games", type=int, default=60)
    p.add_argument("--seed-start", type=int, default=700)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    return run_full(args)


if __name__ == "__main__":
    raise SystemExit(main())

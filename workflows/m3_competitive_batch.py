#!/usr/bin/env python3
"""
M3 competitive batch: Yolanda (adaptive) vs YolandaM2Baseline (frozen M2).

Reports Elo delta, wins, score differential, search stats, and reliability under strict_240 / local_360.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import math
import os
import platform
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _stats_player_a(board) -> tuple[int, int]:
    from game.enums import MoveType

    lb = board.history.left_behind_enums
    rc = board.history.rat_caught
    attempts = correct = 0
    for i, mt in enumerate(lb):
        if i % 2 != 0:
            continue
        if mt != MoveType.SEARCH:
            continue
        attempts += 1
        if rc[i]:
            correct += 1
    return attempts, correct


def _stats_player_b(board) -> tuple[int, int]:
    from game.enums import MoveType

    lb = board.history.left_behind_enums
    rc = board.history.rat_caught
    attempts = correct = 0
    for i, mt in enumerate(lb):
        if i % 2 != 1:
            continue
        if mt != MoveType.SEARCH:
            continue
        attempts += 1
        if rc[i]:
            correct += 1
    return attempts, correct


def _absolute_ab_scores(board) -> tuple[int, int]:
    if board.player_worker.is_player_a:
        return board.player_worker.get_points(), board.opponent_worker.get_points()
    return board.opponent_worker.get_points(), board.player_worker.get_points()


def _m3_lost(m3_is_a: bool, winner) -> bool:
    from game.enums import ResultArbiter

    if winner == ResultArbiter.TIE or winner == ResultArbiter.ERROR:
        return False
    if m3_is_a:
        return winner == ResultArbiter.PLAYER_B
    return winner == ResultArbiter.PLAYER_A


def expected_score(r_a: float, r_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((r_b - r_a) / 400.0))


def update_elo_pair(r_win: float, r_lose: float, score_first: float, k: float = 24.0) -> tuple[float, float]:
    """score_first in {0, 0.5, 1} for first player in the rating pair (M3 bot)."""
    e = expected_score(r_win, r_lose)
    delta = k * (score_first - e)
    return r_win + delta, r_lose - delta


def evaluate_promotion_gate(
    *,
    sample_count: int,
    min_games_for_gate: int,
    mean_delta: float,
    elo_delta: float,
    reliability_timeouts: int,
    reliability_invalid: int,
    reliability_crashes: int,
    m3_timeout_losses: int,
) -> tuple[bool, list[str]]:
    """Return (pass, failure_reasons) for M3->M2 promotion evidence."""
    failures: list[str] = []
    if sample_count < min_games_for_gate:
        failures.append(f"insufficient_sample_count={sample_count} < min_games_for_gate={min_games_for_gate}")
    if mean_delta <= 0.0:
        failures.append(f"mean_score_delta={mean_delta:.3f} <= 0")
    if elo_delta <= 0.0:
        failures.append(f"elo_delta_vs_start={elo_delta:+.3f} <= 0")
    if reliability_timeouts > 0 or reliability_invalid > 0 or reliability_crashes > 0:
        failures.append(
            "reliability_regression "
            f"(timeout={reliability_timeouts}, invalid={reliability_invalid}, crash={reliability_crashes})"
        )
    if m3_timeout_losses > 0:
        failures.append(f"docs/m3_timeout_losses={m3_timeout_losses} > 0")
    return len(failures) == 0, failures


def mean_and_95_ci(samples: list[float]) -> tuple[float, float, float]:
    """Normal-approximation CI for sample mean; deterministic and cheap for CLI reporting."""
    n = len(samples)
    if n == 0:
        return 0.0, 0.0, 0.0
    mean = statistics.fmean(samples)
    if n == 1:
        return mean, mean, mean
    stdev = statistics.stdev(samples)
    half = 1.96 * (stdev / math.sqrt(n))
    return mean, mean - half, mean + half


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("strict", "local"),
        default="strict",
        help="strict: 240s + limit_resources (Linux default); local: 360s, no resource limits",
    )
    parser.add_argument("--games", type=int, default=8, help="Games (each swaps sides once)")
    parser.add_argument("--seed-start", type=int, default=42, help="Base seed for board randomness")
    parser.add_argument(
        "--limit-resources",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override engine resource limits (default: True on Linux when profile=strict)",
    )
    parser.add_argument(
        "--play-time",
        type=int,
        default=None,
        help="Override per-player clock budget (default: 240 strict, 360 local)",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress play_game stdout/stderr")
    parser.add_argument(
        "--write-elo-md",
        type=str,
        default="",
        help="Write markdown summary to this path (repo root relative ok)",
    )
    parser.add_argument("--elo-k", type=float, default=24.0, help="Elo K-factor")
    parser.add_argument(
        "--min-games-for-gate",
        type=int,
        default=1,
        help="Minimum sample count required for promotion gate pass when enforcement is enabled.",
    )
    parser.add_argument(
        "--enforce-promotion-gate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Fail with exit code 1 when M3 promotion evidence regresses: "
            "mean score delta <= 0, Elo delta <= 0, or reliability failures."
        ),
    )
    args = parser.parse_args()

    if args.profile == "strict":
        play_time = args.play_time if args.play_time is not None else 240
        limit_resources = (
            args.limit_resources if args.limit_resources is not None else platform.system() == "Linux"
        )
    else:
        play_time = args.play_time if args.play_time is not None else 360
        limit_resources = args.limit_resources if args.limit_resources is not None else False

    sys.path.insert(0, str(ROOT / "engine"))
    sys.path.insert(0, str(ROOT / "3600-agents"))
    from game.enums import ResultArbiter, WinReason
    from gameplay import play_game

    play_dir = os.path.join(str(ROOT), "3600-agents")

    m3_att = m3_cor = b_att = b_cor = 0
    m3_wins = ties = 0
    sum_delta = 0.0
    n_delta = 0
    delta_samples: list[float] = []
    score_samples: list[float] = []

    rel_timeout = rel_invalid = rel_crash = 0
    m3_timeout_losses = 0

    r_m3 = 1500.0
    r_base = 1500.0

    with contextlib.ExitStack() as stack:
        if args.quiet:
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))

        for g in range(args.games):
            random.seed(args.seed_start + g)
            m3_is_a = g % 2 == 0
            if m3_is_a:
                board, *_ = play_game(
                    play_dir,
                    play_dir,
                    "Yolanda",
                    "YolandaM2Baseline",
                    display_game=False,
                    delay=0,
                    clear_screen=False,
                    record=True,
                    limit_resources=limit_resources,
                    play_time_override=play_time,
                )
                sa, sb = _absolute_ab_scores(board)
                m3_score, bs = sa, sb
                a_a, a_c = _stats_player_a(board)
                b_a, b_c = _stats_player_b(board)
                m3_att += a_a
                m3_cor += a_c
                b_att += b_a
                b_cor += b_c
            else:
                board, *_ = play_game(
                    play_dir,
                    play_dir,
                    "YolandaM2Baseline",
                    "Yolanda",
                    display_game=False,
                    delay=0,
                    clear_screen=False,
                    record=True,
                    limit_resources=limit_resources,
                    play_time_override=play_time,
                )
                sa, sb = _absolute_ab_scores(board)
                m3_score, bs = sb, sa
                a_a, a_c = _stats_player_a(board)
                b_a, b_c = _stats_player_b(board)
                m3_att += b_a
                m3_cor += b_c
                b_att += a_a
                b_cor += a_c

            w = board.winner
            reason = board.win_reason

            if w == ResultArbiter.TIE:
                ties += 1
                s_m3 = 0.5
            elif (w == ResultArbiter.PLAYER_A and m3_is_a) or (
                w == ResultArbiter.PLAYER_B and not m3_is_a
            ):
                m3_wins += 1
                s_m3 = 1.0
            else:
                s_m3 = 0.0

            if m3_is_a:
                r_m3, r_base = update_elo_pair(r_m3, r_base, s_m3, k=args.elo_k)
            else:
                r_base, r_m3 = update_elo_pair(r_base, r_m3, 1.0 - s_m3, k=args.elo_k)

            delta = float(m3_score - bs)
            sum_delta += delta
            n_delta += 1
            delta_samples.append(delta)
            score_samples.append(s_m3)

            if reason == WinReason.TIMEOUT:
                rel_timeout += 1
            elif reason == WinReason.INVALID_TURN:
                rel_invalid += 1
            elif reason in (WinReason.CODE_CRASH, WinReason.MEMORY_ERROR):
                rel_crash += 1

            if reason == WinReason.TIMEOUT and _m3_lost(m3_is_a, w):
                m3_timeout_losses += 1

    def rate(num: int, den: int) -> float:
        return float(num) / den if den else 0.0

    mean_delta = sum_delta / n_delta if n_delta else 0.0
    elo_delta = r_m3 - 1500.0
    score_mean, score_ci_lo, score_ci_hi = mean_and_95_ci(score_samples)
    delta_mean, delta_ci_lo, delta_ci_hi = mean_and_95_ci(delta_samples)
    gate_pass, gate_failures = evaluate_promotion_gate(
        sample_count=n_delta,
        min_games_for_gate=args.min_games_for_gate,
        mean_delta=mean_delta,
        elo_delta=elo_delta,
        reliability_timeouts=rel_timeout,
        reliability_invalid=rel_invalid,
        reliability_crashes=rel_crash,
        m3_timeout_losses=m3_timeout_losses,
    )

    lines_out = [
        f"M3 competitive batch profile={args.profile} play_time={play_time} "
        f"limit_resources={limit_resources}",
        f"games={args.games} seed_start={args.seed_start} elo_k={args.elo_k}",
        f"Yolanda(M3) wins={m3_wins} ties={ties} YolandaM2Baseline wins={args.games - m3_wins - ties}",
        f"Mean score delta (M3 - M2 baseline)={mean_delta:.3f}",
        f"Mean score delta 95% CI=[{delta_ci_lo:.3f}, {delta_ci_hi:.3f}]",
        f"M3 match score mean (win=1,tie=0.5)={score_mean:.3f}",
        f"M3 match score mean 95% CI=[{score_ci_lo:.3f}, {score_ci_hi:.3f}]",
        f"Elo(M3)={r_m3:.1f} Elo(M2)={r_base:.1f} delta_vs_start={elo_delta:+.1f}",
        f"M3 search: attempts={m3_att} correct={m3_cor} precision={rate(m3_cor, m3_att):.4f}",
        f"M2 baseline search: attempts={b_att} correct={b_cor} precision={rate(b_cor, b_att):.4f}",
        f"Reliability (all games): timeout={rel_timeout} invalid={rel_invalid} crash={rel_crash}",
        f"M3 timeout losses={m3_timeout_losses}",
        (
            "Promotion gate: PASS (mean_score_delta>0, elo_delta>0, reliability clean)"
            if gate_pass
            else "Promotion gate: FAIL " + "; ".join(gate_failures)
        ),
    ]
    text = "\n".join(lines_out)
    print(text)

    if args.write_elo_md:
        out_path = Path(args.write_elo_md)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        interpretation = (
            "Gate status: PASS. Mean score delta and Elo delta are both positive, with no reliability regressions."
            if gate_pass
            else "Gate status: FAIL. M3 does not satisfy promotion evidence requirements in this run."
        )
        failures_section = ""
        if gate_failures:
            failures_md = "\n".join(f"- {msg}" for msg in gate_failures)
            failures_section = f"""

Promotion gate failure reasons:
{failures_md}
"""

        md = f"""# M3 Elo uplift vs M2 baseline

Generated by `workflows/m3_competitive_batch.py` (see console block for parameters).

## Summary

- **Opponents**: `Yolanda` (M3 adaptive) vs `YolandaM2Baseline` (frozen M2 snapshot).
- **Elo model**: standard expected score `1/(1+10^((Rb-Ra)/400))`, K={args.elo_k}, both start 1500.
- **Elo delta (M3 - start)**: {elo_delta:+.2f} (final M3 rating {r_m3:.1f} vs baseline {r_base:.1f}).
- **Mean score delta (M3 - M2)**: {delta_mean:.3f}, 95% CI [{delta_ci_lo:.3f}, {delta_ci_hi:.3f}].
- **M3 match score mean** (`win=1`, `tie=0.5`, `loss=0`): {score_mean:.3f}, 95% CI [{score_ci_lo:.3f}, {score_ci_hi:.3f}].
- **Promotion minimum sample requirement**: {args.min_games_for_gate} games.

## Batch metrics

```
{text}
```

## Interpretation

{interpretation}
{failures_section}

## Mandatory scenarios (M3)

See `bot_plan_v4.md` mandatory scenario list; local coverage is provided by `tests/` + `workflows/quality_guard.py`.
Platform George/Albert/Carrie gates remain external to this repo.
"""
        out_path.write_text(md, encoding="utf-8")

    if args.enforce_promotion_gate and not gate_pass:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

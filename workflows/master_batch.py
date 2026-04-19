#!/usr/bin/env python3
"""
Master batch simulation runner.
Matches any two bots from '3600-agents/' against each other.
Aligned with engine/run_local_agents.py logic.
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
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / "3600-agents"


def _discover_bot_names() -> list[str]:
    names: list[str] = []
    if not AGENTS_DIR.is_dir():
        return names
    for p in sorted(AGENTS_DIR.iterdir()):
        if p.is_dir() and (p / "agent.py").is_file():
            names.append(p.name)
    return names


def _validate_bot(name: str) -> None:
    agent_py = AGENTS_DIR / name / "agent.py"
    if not agent_py.is_file():
        raise argparse.ArgumentTypeError(f"no agent package '{name}' (expected {agent_py})")


def _stats_player_a(board) -> tuple[int, int]:
    """Extract search attempts and catches for Player A from history."""
    from game.enums import MoveType

    if not board.history:
        return 0, 0
    lb = board.history.left_behind_enums
    rc = board.history.rat_caught
    attempts = correct = 0
    for i, mt in enumerate(lb):
        if i % 2 != 0:  # Player B turns
            continue
        if mt == MoveType.SEARCH:
            attempts += 1
            if rc[i]:
                correct += 1
    return attempts, correct


def _stats_player_b(board) -> tuple[int, int]:
    """Extract search attempts and catches for Player B from history."""
    from game.enums import MoveType

    if not board.history:
        return 0, 0
    lb = board.history.left_behind_enums
    rc = board.history.rat_caught
    attempts = correct = 0
    for i, mt in enumerate(lb):
        if i % 2 != 1:  # Player A turns
            continue
        if mt == MoveType.SEARCH:
            attempts += 1
            if rc[i]:
                correct += 1
    return attempts, correct


def _absolute_ab_scores(board) -> tuple[int, int]:
    """Returns (Points A, Points B) regardless of whose turn it is."""
    if board.player_worker.is_player_a:
        return board.player_worker.get_points(), board.opponent_worker.get_points()
    return board.opponent_worker.get_points(), board.player_worker.get_points()


def _run_game_task(
    g: int,
    seed_start: int,
    a_name: str,
    b_name: str,
    play_dir: str,
    limit_resources: bool,
    play_time: int,
    alternate_sides: bool,
    quiet: bool,
    root_path: str,
):
    import random
    import sys
    import contextlib
    import io
    import os
    from pathlib import Path

    # This is needed inside the worker
    p_root = Path(root_path)
    if str(p_root / "engine") not in sys.path:
        sys.path.insert(0, str(p_root / "engine"))
    if str(p_root / "3600-agents") not in sys.path:
        sys.path.insert(0, str(p_root / "3600-agents"))

    from gameplay import play_game

    random.seed(seed_start + g)
    first_is_a = (g % 2 == 0) if alternate_sides else True
    p1, p2 = (a_name, b_name) if first_is_a else (b_name, a_name)

    # Use a dummy context if not quiet, otherwise redirect
    with contextlib.ExitStack() as stack:
        if quiet:
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))

        board, *_ = play_game(
            play_dir,
            play_dir,
            p1,
            p2,
            display_game=False,
            delay=0,
            clear_screen=False,
            record=True,
            limit_resources=limit_resources,
            play_time_override=play_time,
        )

    sa, sb = _absolute_ab_scores(board)
    aa, ac = _stats_player_a(board)
    ba, bc = _stats_player_b(board)

    return {
        "g": g,
        "winner": board.winner,
        "win_reason": board.win_reason,
        "first_is_a": first_is_a,
        "sa": sa,
        "sb": sb,
        "aa": aa,
        "ac": ac,
        "ba": ba,
        "bc": bc,
    }


def expected_score(r_a: float, r_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((r_b - r_a) / 400.0))


def update_elo_pair(r_1: float, r_2: float, score_1: float, k: float = 24.0) -> tuple[float, float]:
    """Updates Elo for a pair. score_1 is 1.0 (win), 0.5 (tie), 0.0 (loss)."""
    e = expected_score(r_1, r_2)
    delta = k * (score_1 - e)
    return r_1 + delta, r_2 - delta


def mean_and_95_ci(samples: list[float]) -> tuple[float, float, float]:
    """Calculates mean and 95% confidence interval using normal approximation."""
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
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "bot_first",
        nargs="?",
        help="First bot (package name under 3600-agents); reference for score delta and win counts",
    )
    parser.add_argument(
        "bot_second",
        nargs="?",
        help="Second bot package name",
    )
    parser.add_argument(
        "--profile",
        choices=("strict", "local"),
        default="strict",
        help="Profile for timing and limits (default: strict)",
    )
    parser.add_argument("--games", type=int, default=8, help="Total games (alternates sides unless specified)")
    parser.add_argument("--seed-start", type=int, default=42, help="Base seed for reproducibility")
    parser.add_argument(
        "--alternate-sides",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Alternate player A/B roles between games",
    )
    parser.add_argument(
        "--limit-resources",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override resource limits (default matches profile)",
    )
    parser.add_argument(
        "--play-time",
        type=int,
        default=None,
        help="Override per-player time (default matches profile)",
    )
    parser.add_argument("--elo-k", type=float, default=24.0, help="K-factor for Elo calculation")
    parser.add_argument("--parallel", action="store_true", help="Run games in parallel")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers (default: 4)")
    parser.add_argument("--quiet", action="store_true", help="Suppress bot stdout/stderr")
    parser.add_argument("--list-bots", action="store_true", help="List available bots and exit")
    args = parser.parse_args()

    if args.list_bots:
        bots = _discover_bot_names()
        if not bots:
            print(f"No bots found under {AGENTS_DIR}")
            return 1
        print("Available bots in 3600-agents:")
        for b in bots:
            print(f"  - {b}")
        return 0

    if not args.bot_first or not args.bot_second:
        parser.error("bot_first and bot_second are required unless --list-bots is used.")

    try:
        _validate_bot(args.bot_first)
        _validate_bot(args.bot_second)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))

    # Resolve Profile Logic
    if args.profile == "strict":
        play_time = args.play_time if args.play_time is not None else 240
        limit_resources = (
            args.limit_resources if args.limit_resources is not None else platform.system() == "Linux"
        )
    else:
        play_time = args.play_time if args.play_time is not None else 360
        limit_resources = args.limit_resources if args.limit_resources is not None else False

    # Setup Environment
    sys.path.insert(0, str(ROOT / "engine"))
    sys.path.insert(0, str(ROOT / "3600-agents"))
    try:
        from game.enums import ResultArbiter, WinReason
        from gameplay import play_game
    except ModuleNotFoundError:
        print("Error: Engine dependencies not found. Please install requirements.txt.", file=sys.stderr)
        return 1

    a_name, b_name = args.bot_first, args.bot_second
    play_dir = str(AGENTS_DIR)

    # Statistics
    first_wins = second_wins = ties = errors = 0
    rel_timeout = rel_invalid = rel_crash = 0
    f_att = f_cor = s_att = s_cor = 0
    f_to_loss = s_to_loss = 0
    
    delta_samples = []
    score_samples = []  # 1.0 for first win, 0.5 for tie
    r_first, r_second = 1500.0, 1500.0

    print(f"Batch: {a_name} vs {b_name} | games={args.games} profile={args.profile}")
    print(f"Settings: play_time={play_time} limit_resources={limit_resources}\n")

    results = []
    if args.parallel:
        print(f"Running {args.games} games in parallel with {args.workers} workers...")
        task = partial(
            _run_game_task,
            seed_start=args.seed_start,
            a_name=a_name,
            b_name=b_name,
            play_dir=play_dir,
            limit_resources=limit_resources,
            play_time=play_time,
            alternate_sides=args.alternate_sides,
            quiet=args.quiet,
            root_path=str(ROOT),
        )
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(task, g) for g in range(args.games)]
            for i, future in enumerate(as_completed(futures)):
                res = future.result()
                results.append(res)
                sys.__stdout__.write(f"\rFinished {len(results)}/{args.games} games...")
                sys.__stdout__.flush()
        print("\nAll games finished. Processing results...")
    else:
        with contextlib.ExitStack() as stack:
            if args.quiet:
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                stack.enter_context(contextlib.redirect_stderr(io.StringIO()))

            for g in range(args.games):
                random.seed(args.seed_start + g)
                first_is_a = (g % 2 == 0) if args.alternate_sides else True
                p1, p2 = (a_name, b_name) if first_is_a else (b_name, a_name)
                
                board, *_ = play_game(
                    play_dir,
                    play_dir,
                    p1,
                    p2,
                    display_game=False,
                    delay=0,
                    clear_screen=False,
                    record=True,
                    limit_resources=limit_resources,
                    play_time_override=play_time,
                )

                sa, sb = _absolute_ab_scores(board)
                aa, ac = _stats_player_a(board)
                ba, bc = _stats_player_b(board)

                results.append({
                    "g": g,
                    "winner": board.winner,
                    "win_reason": board.win_reason,
                    "first_is_a": first_is_a,
                    "sa": sa, "sb": sb,
                    "aa": aa, "ac": ac,
                    "ba": ba, "bc": bc
                })
                print(f"Finished {g+1}/{args.games} games.")

    # Sort results to ensure Elo updates are in order
    results.sort(key=lambda x: x["g"])

    from game.enums import ResultArbiter, WinReason
    for res in results:
        w = res["winner"]
        reason = res["win_reason"]
        first_is_a = res["first_is_a"]
        sa, sb = res["sa"], res["sb"]
        aa, ac = res["aa"], res["ac"]
        ba, bc = res["ba"], res["bc"]

        # Map winners
        s_val = 0.5
        if w == ResultArbiter.TIE:
            ties += 1
        elif (w == ResultArbiter.PLAYER_A and first_is_a) or (
            w == ResultArbiter.PLAYER_B and not first_is_a
        ):
            first_wins += 1
            s_val = 1.0
        elif w == ResultArbiter.ERROR:
            errors += 1
        else:
            second_wins += 1
            s_val = 0.0

        # Elo
        if first_is_a:
            r_first, r_second = update_elo_pair(r_first, r_second, s_val, k=args.elo_k)
        else:
            r_second, r_first = update_elo_pair(r_second, r_first, 1.0 - s_val, k=args.elo_k)

        # Reliability
        if reason == WinReason.TIMEOUT:
            rel_timeout += 1
            if s_val == 0.0: f_to_loss += 1
            if s_val == 1.0 and w != ResultArbiter.TIE: s_to_loss += 1
        elif reason == WinReason.INVALID_TURN:
            rel_invalid += 1
        elif reason in (WinReason.CODE_CRASH, WinReason.MEMORY_ERROR):
            rel_crash += 1

        # Points
        f_sc, s_sc = (sa, sb) if first_is_a else (sb, sa)
        delta_samples.append(float(f_sc - s_sc))
        score_samples.append(s_val)

        # Search
        if first_is_a:
            f_att += aa; f_cor += ac
            s_att += ba; s_cor += bc
        else:
            f_att += ba; f_cor += bc
            s_att += aa; s_cor += ac

    def rate(num: int, den: int) -> float:
        return float(num) / den if den else 0.0

    d_mean, d_lo, d_hi = mean_and_95_ci(delta_samples)
    s_mean, s_lo, s_hi = mean_and_95_ci(score_samples)

    output = []
    output.append("\n" + "="*40)
    output.append(f"FINAL SUMMARY: {a_name} vs {b_name}")
    output.append("="*40)
    output.append(f"Wins: {a_name}={first_wins}, {b_name}={second_wins}, Ties={ties}, Errors={errors}")
    output.append(f"Match Score Mean ({a_name}): {s_mean:.3f} 95% CI: [{s_lo:.3f}, {s_hi:.3f}]")
    output.append(f"Mean Point Delta: {d_mean:+.2f} 95% CI: [{d_lo:.2f}, {d_hi:.2f}]")
    output.append(f"Elo: {a_name}={r_first:.1f}, {b_name}={r_second:.1f} \u0394={r_first - 1500.0:+.1f}")
    output.append("-" * 40)
    output.append(f"{a_name:20} Search Precision: {rate(f_cor, f_att):.4f} ({f_cor}/{f_att})")
    output.append(f"{b_name:20} Search Precision: {rate(s_cor, s_att):.4f} ({s_cor}/{s_att})")
    output.append("-" * 40)
    output.append(f"Reliability (Total): Timeouts={rel_timeout}, Invalid={rel_invalid}, Crashes={rel_crash}")
    output.append(f"Timeout Losses: {a_name}={f_to_loss}, {b_name}={s_to_loss}")
    output.append("="*40)
    
    # Use direct print to bypass StringIO if quiet was on
    sys.__stdout__.write("\n".join(output) + "\n")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(1)

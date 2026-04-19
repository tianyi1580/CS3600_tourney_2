#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "engine") not in sys.path:
    sys.path.insert(0, str(ROOT / "engine"))
if str(ROOT / "3600-agents") not in sys.path:
    sys.path.insert(0, str(ROOT / "3600-agents"))

from gameplay import play_game
from game.enums import ResultArbiter


def absolute_scores(board) -> tuple[int, int]:
    if board.player_worker.is_player_a:
        return board.player_worker.get_points(), board.opponent_worker.get_points()
    return board.opponent_worker.get_points(), board.player_worker.get_points()


def run_series(agent_a: str, agent_b: str, games: int, seed_start: int, play_time: int) -> dict[str, float | int]:
    play_dir = str(ROOT / "3600-agents")
    deltas: list[int] = []
    wins = losses = ties = catastrophic_losses = 0

    for game_idx in range(games):
        random.seed(seed_start + game_idx)
        board, *_ = play_game(
            play_dir,
            play_dir,
            agent_a,
            agent_b,
            display_game=False,
            delay=0,
            clear_screen=False,
            record=True,
            limit_resources=False,
            play_time_override=play_time,
        )
        a_score, b_score = absolute_scores(board)
        delta = a_score - b_score
        deltas.append(delta)
        if board.winner == ResultArbiter.TIE:
            ties += 1
        elif board.winner == ResultArbiter.PLAYER_A:
            wins += 1
        else:
            losses += 1
        if delta <= -15:
            catastrophic_losses += 1

    return {
        "games": games,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "mean_delta": sum(deltas) / len(deltas) if deltas else 0.0,
        "catastrophic_losses": catastrophic_losses,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a small head-to-head validation series.")
    parser.add_argument("agent_a")
    parser.add_argument("agent_b")
    parser.add_argument("--games", type=int, default=4)
    parser.add_argument("--seed-start", type=int, default=100)
    parser.add_argument("--play-time", type=int, default=120)
    args = parser.parse_args()

    result = run_series(args.agent_a, args.agent_b, args.games, args.seed_start, args.play_time)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

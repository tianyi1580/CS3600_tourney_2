#!/usr/bin/env python3
import sys
import os
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "3600-agents"))

from gameplay import play_game
from game.enums import ResultArbiter

OPPONENTS = ["Yolanda3_2", "Yolanda3_3", "yolanda_mitchell"]
GAMES_PER_OPPONENT = 1

def parse_metrics(commentary: str) -> dict:
    metrics = {
        "trap_freq": 0.0,
        "trap_search": 0,
        "trap_rate": 0.0,
        "low_ev_trap": 0,
        "rollout_exceed_rate": 0.0
    }
    # Parse format: trap_freq=0.12 trap_search=3 trap_rate=0.25 low_ev_trap=1 rollout_exceed_rate=0.05
    for key in metrics.keys():
        match = re.search(fr"{key}=([\d\.]+)", commentary)
        if match:
            if isinstance(metrics[key], int):
                metrics[key] = int(match.group(1).split('.')[0])
            else:
                metrics[key] = float(match.group(1))
    return metrics

def main():
    print(f"Starting Yolanda3_4 Scrim Metrics Workflow...")
    print(f"Opponents: {OPPONENTS}")
    print(f"Games per opponent: {GAMES_PER_OPPONENT} (swapping sides)")
    
    results = []
    
    for opp in OPPONENTS:
        print(f"\nEvaluating against {opp}...")
        for g in range(GAMES_PER_OPPONENT):
            y_is_a = g % 2 == 0
            if y_is_a:
                pa, pb = "Yolanda3_4", opp
            else:
                pa, pb = opp, "Yolanda3_4"
            
            random.seed(42 + g)
            board, _, _, _, msg_a, msg_b = play_game(
                str(ROOT / "3600-agents"),
                str(ROOT / "3600-agents"),
                pa, pb,
                display_game=False,
                limit_resources=False,
                play_time_override=240
            )
            
            y_msg = msg_a if y_is_a else msg_b
            y_points = board.player_worker.get_points() if y_is_a else board.opponent_worker.get_points()
            opp_points = board.opponent_worker.get_points() if y_is_a else board.player_worker.get_points()
            
            win = 0
            if board.winner == ResultArbiter.PLAYER_A and y_is_a: win = 1
            elif board.winner == ResultArbiter.PLAYER_B and not y_is_a: win = 1
            elif board.winner == ResultArbiter.TIE: win = 0.5
            
            metrics = parse_metrics(y_msg)
            results.append({
                "opp": opp,
                "win": win,
                "score_delta": y_points - opp_points,
                **metrics
            })
            print(f"  Game {g+1}: Win={win}, Delta={y_points - opp_points}, TrapFreq={metrics['trap_freq']:.2f}")

    # Aggregate
    agg = {
        "win_rate": sum(r["win"] for r in results) / len(results),
        "avg_delta": sum(r["score_delta"] for r in results) / len(results),
        "avg_trap_freq": sum(r["trap_freq"] for r in results) / len(results),
        "total_low_ev": sum(r["low_ev_trap"] for r in results),
        "total_trap_searches": sum(r["trap_search"] for r in results),
        "avg_rollout_exceed": sum(r["rollout_exceed_rate"] for r in results) / len(results)
    }
    
    print("\n" + "="*50)
    print("YOLANDA3_4 SCRIM SUMMARY")
    print("="*50)
    print(f"Win Rate:            {agg['win_rate']:.1%}")
    print(f"Avg Score Delta:     {agg['avg_delta']:+.2f}")
    print(f"Avg Trap-State Freq: {agg['avg_trap_freq']:.2%}")
    print(f"Total Trap Searches: {agg['total_trap_searches']}")
    print(f"Total Low-EV Brakes: {agg['total_low_ev']}")
    print(f"Avg Rollout Exceed:  {agg['avg_rollout_exceed']:.2%}")
    print("="*50)

if __name__ == "__main__":
    main()

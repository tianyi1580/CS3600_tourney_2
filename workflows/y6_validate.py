#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MASTER_BATCH = ROOT / "workflows" / "master_batch.py"
DEFAULT_OPPONENTS = ("Yolanda5", "yolanda_prime_v1_1")

_WINS_RE = re.compile(r"Wins:\s+(?P<first>\w+)=(?P<first_wins>\d+),\s+(?P<second>\w+)=(?P<second_wins>\d+),\s+Ties=(?P<ties>\d+),\s+Errors=(?P<errors>\d+)")
_MATCH_RE = re.compile(r"Match Score Mean \((?P<name>\w+)\):\s+(?P<mean>[-+0-9.]+)")
_DELTA_RE = re.compile(r"Mean Point Delta:\s+(?P<mean>[-+0-9.]+)")
_REL_RE = re.compile(r"Reliability \(Total\): Timeouts=(?P<timeouts>\d+), Invalid=(?P<invalid>\d+), Crashes=(?P<crashes>\d+)")
_TIMEOUT_LOSS_RE = re.compile(r"Timeout Losses:\s+(?P<first>\w+)=(?P<first_losses>\d+),\s+(?P<second>\w+)=(?P<second_losses>\d+)")


def _run_series(opponent: str, games: int, seed_start: int) -> dict[str, object]:
    cmd = [
        sys.executable,
        str(MASTER_BATCH),
        "Yolanda6",
        opponent,
        "--profile",
        "strict",
        "--games",
        str(games),
        "--seed-start",
        str(seed_start),
        "--quiet",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True)
    summary = _parse_summary(proc.stdout)
    summary["opponent"] = opponent
    summary["games"] = games
    return summary


def _parse_summary(stdout: str) -> dict[str, object]:
    data: dict[str, object] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        wins_match = _WINS_RE.search(line)
        if wins_match:
            data["wins"] = int(wins_match.group("first_wins"))
            data["losses"] = int(wins_match.group("second_wins"))
            data["ties"] = int(wins_match.group("ties"))
            data["errors"] = int(wins_match.group("errors"))
            continue
        match_score = _MATCH_RE.search(line)
        if match_score:
            data["match_score_mean"] = float(match_score.group("mean"))
            continue
        delta_match = _DELTA_RE.search(line)
        if delta_match:
            data["mean_point_delta"] = float(delta_match.group("mean"))
            continue
        rel_match = _REL_RE.search(line)
        if rel_match:
            data["timeouts"] = int(rel_match.group("timeouts"))
            data["invalid"] = int(rel_match.group("invalid"))
            data["crashes"] = int(rel_match.group("crashes"))
            continue
        timeout_loss_match = _TIMEOUT_LOSS_RE.search(line)
        if timeout_loss_match:
            data["timeout_losses"] = int(timeout_loss_match.group("first_losses"))
    return data


def _passes_gate(summary: dict[str, object], games: int) -> bool:
    wins = int(summary.get("wins", 0))
    win_rate = wins / games if games else 0.0
    return (
        win_rate > 0.55
        and float(summary.get("mean_point_delta", 0.0)) > 0.0
        and int(summary.get("invalid", 0)) == 0
        and int(summary.get("timeout_losses", 0)) == 0
        and int(summary.get("crashes", 0)) == 0
        and int(summary.get("errors", 0)) == 0
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Yolanda6 strict promotion gate against fixed baselines.")
    parser.add_argument("--games", type=int, default=200, help="Strict-profile games per opponent")
    parser.add_argument("--seed-start", type=int, default=42, help="Base seed for reproducibility")
    parser.add_argument("--opponents", nargs="*", default=list(DEFAULT_OPPONENTS), help="Opponent package names")
    args = parser.parse_args()

    summaries: list[dict[str, object]] = []
    for offset, opponent in enumerate(args.opponents):
        summary = _run_series(opponent, args.games, args.seed_start + offset * 10_000)
        summary["passes_gate"] = _passes_gate(summary, args.games)
        summaries.append(summary)

    overall_pass = all(bool(summary["passes_gate"]) for summary in summaries)
    payload = {
        "games_per_opponent": args.games,
        "strict_profile": True,
        "overall_pass": overall_pass,
        "series": summaries,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"promotion_gate={'PASS' if overall_pass else 'FAIL'} opponents={','.join(args.opponents)} games={args.games}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

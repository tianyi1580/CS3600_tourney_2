#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflows.y4_hyperopt import available_profiles, clamp_weights, evaluate_series


def _load_weights(args: argparse.Namespace) -> dict[str, float]:
    if args.weights_file:
        return json.loads(Path(args.weights_file).read_text(encoding="utf-8"))
    if args.weights_json:
        return json.loads(args.weights_json)
    return {}


def _load_baseline_weights(args: argparse.Namespace) -> dict[str, float] | None:
    if not args.baseline_weights_file:
        return None
    return json.loads(Path(args.baseline_weights_file).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate one Yolanda4 weight vector against one opponent.")
    parser.add_argument("opponent", help="Opponent package name under 3600-agents/")
    parser.add_argument("--weights-json", help="Inline JSON object of candidate overrides")
    parser.add_argument("--weights-file", help="Path to a JSON file of candidate overrides")
    parser.add_argument("--baseline-weights-file", help="Optional JSON file for the Yolanda4Baseline wrapper")
    parser.add_argument("--games", type=int, default=40, help="Number of games to run")
    parser.add_argument("--seed-start", type=int, default=42, help="Base seed for reproducibility")
    parser.add_argument(
        "--profile",
        choices=available_profiles(),
        default="tuning",
        help="smoke=30s/no sandbox, tuning=240s/no sandbox, strict=240s/limits, local=360s/no limits",
    )
    parser.add_argument("--workers", type=int, default=1, help="Parallel game workers for this one opponent")
    parser.add_argument("--catastrophic-penalty", type=float, default=-50.0, help="Margin assigned to candidate catastrophic losses")
    args = parser.parse_args()

    weights = clamp_weights(_load_weights(args))
    baseline_weights = _load_baseline_weights(args)
    result = evaluate_series(
        weights,
        args.opponent,
        games=args.games,
        seed_start=args.seed_start,
        profile=args.profile,
        workers=max(1, args.workers),
        catastrophic_penalty=args.catastrophic_penalty,
        baseline_weights=baseline_weights,
    )
    print(json.dumps(result.__dict__, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

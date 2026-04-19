#!/usr/bin/env python3
"""
Run M3 ablations against M2 baseline and write markdown evidence.

Ablation knobs:
- YOLANDA_ENABLE_OPPONENT_MODEL
- YOLANDA_ENABLE_ADAPTIVE_MARGIN
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class AblationConfig:
    name: str
    opponent_model: bool
    adaptive_margin: bool


@dataclass
class AblationResult:
    cfg: AblationConfig
    mean_delta: float
    elo_delta: float
    search_precision: float
    promotion_gate: str
    raw_output: str


RE_MEAN_DELTA = re.compile(r"Mean score delta \(M3 - M2 baseline\)=([+-]?\d+(?:\.\d+)?)")
RE_ELO_DELTA = re.compile(r"delta_vs_start=([+-]?\d+(?:\.\d+)?)")
RE_SEARCH_PREC = re.compile(r"M3 search: attempts=\d+ correct=\d+ precision=([0-9.]+)")
RE_GATE = re.compile(r"Promotion gate:\s*(PASS|FAIL)\b(.*)")


def parse_metric(text: str, pattern: re.Pattern[str], metric_name: str) -> str:
    m = pattern.search(text)
    if not m:
        raise RuntimeError(f"Unable to parse {metric_name} from m3_competitive_batch output")
    return m.group(1)


def evaluate_ablation_enforcement(results: list[AblationResult]) -> list[str]:
    """
    Enforce that full M3 is both absolutely viable and not outperformed by simpler configs.
    """
    by_name = {r.cfg.name: r for r in results}
    full = by_name["full_m3"]
    alt_best = max((r for r in results if r.cfg.name != "full_m3"), key=lambda r: r.mean_delta)

    failures: list[str] = []
    if full.mean_delta <= 0.0:
        failures.append(f"full_m3_mean_delta={full.mean_delta:.3f} <= 0")
    if full.elo_delta <= 0.0:
        failures.append(f"full_m3_elo_delta={full.elo_delta:+.3f} <= 0")
    if full.promotion_gate != "PASS":
        failures.append(f"full_m3_gate={full.promotion_gate} != PASS")
    if full.mean_delta < alt_best.mean_delta:
        failures.append(
            f"full_m3_mean_delta={full.mean_delta:.3f} < best_ablation({alt_best.cfg.name})={alt_best.mean_delta:.3f}"
        )
    return failures


def run_single(cfg: AblationConfig, *, games: int, seed_start: int, profile: str, python_bin: str) -> AblationResult:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT / 'engine'}:{ROOT / '3600-agents'}:{env.get('PYTHONPATH', '')}"
    env["YOLANDA_ENABLE_OPPONENT_MODEL"] = "1" if cfg.opponent_model else "0"
    env["YOLANDA_ENABLE_ADAPTIVE_MARGIN"] = "1" if cfg.adaptive_margin else "0"

    cmd = [
        python_bin,
        str(ROOT / "workflows" / "docs/m3_competitive_batch.py"),
        "--games",
        str(games),
        "--quiet",
        "--profile",
        profile,
        "--seed-start",
        str(seed_start),
        "--min-games-for-gate",
        str(games),
        "--no-enforce-promotion-gate",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ablation run failed for {cfg.name}:\n{proc.stdout}")

    out = proc.stdout
    mean_delta = float(parse_metric(out, RE_MEAN_DELTA, "mean score delta"))
    elo_delta = float(parse_metric(out, RE_ELO_DELTA, "elo delta"))
    search_precision = float(parse_metric(out, RE_SEARCH_PREC, "search precision"))
    gate_m = RE_GATE.search(out)
    promotion_gate = gate_m.group(1) if gate_m else "UNKNOWN"

    return AblationResult(
        cfg=cfg,
        mean_delta=mean_delta,
        elo_delta=elo_delta,
        search_precision=search_precision,
        promotion_gate=promotion_gate,
        raw_output=out.strip(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=40, help="Games per ablation config")
    parser.add_argument("--seed-start", type=int, default=42, help="Seed start per ablation config")
    parser.add_argument("--profile", choices=("strict", "local"), default="strict")
    parser.add_argument("--python-bin", type=str, default=sys.executable)
    parser.add_argument(
        "--write-md",
        type=str,
        default=str(ROOT / "docs/m3_ablation_matrix_report.md"),
        help="Markdown output path",
    )
    parser.add_argument(
        "--enforce",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fail if full M3 is outperformed by a simpler ablation config on mean score delta.",
    )
    args = parser.parse_args()

    configs = [
        AblationConfig("full_m3", opponent_model=True, adaptive_margin=True),
        AblationConfig("no_adaptive_margin", opponent_model=True, adaptive_margin=False),
        AblationConfig("no_opponent_model", opponent_model=False, adaptive_margin=True),
        AblationConfig("no_model_no_margin", opponent_model=False, adaptive_margin=False),
    ]

    results: list[AblationResult] = []
    for cfg in configs:
        print(
            f"[ablation] {cfg.name}: opponent_model={cfg.opponent_model} "
            f"adaptive_margin={cfg.adaptive_margin}"
        )
        results.append(
            run_single(
                cfg,
                games=args.games,
                seed_start=args.seed_start,
                profile=args.profile,
                python_bin=args.python_bin,
            )
        )

    enforce_fail_reasons = evaluate_ablation_enforcement(results)

    lines: list[str] = []
    lines.append("# M3 ablation matrix report")
    lines.append("")
    lines.append("Generated by `workflows/m3_ablation_matrix.py`.")
    lines.append("")
    lines.append("## Settings")
    lines.append(f"- profile: `{args.profile}`")
    lines.append(f"- games per config: `{args.games}`")
    lines.append(f"- seed_start: `{args.seed_start}`")
    lines.append("")
    lines.append("## Summary table")
    lines.append("")
    lines.append("| config | opponent_model | adaptive_margin | mean_score_delta | elo_delta_vs_start | m3_search_precision | m3_gate |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: | --- |")
    for r in results:
        lines.append(
            "| "
            f"{r.cfg.name} | {r.cfg.opponent_model} | {r.cfg.adaptive_margin} | "
            f"{r.mean_delta:.3f} | {r.elo_delta:+.3f} | {r.search_precision:.4f} | {r.promotion_gate} |"
        )
    lines.append("")
    lines.append("## Enforcement")
    if enforce_fail_reasons:
        lines.append("- status: **FAIL**")
        for reason in enforce_fail_reasons:
            lines.append(f"- {reason}")
    else:
        lines.append("- status: **PASS**")
        lines.append("- full_m3 passes absolute viability and relative ablation checks.")
    lines.append("")
    lines.append("## Raw outputs")
    for r in results:
        lines.append(f"### {r.cfg.name}")
        lines.append("```")
        lines.append(r.raw_output)
        lines.append("```")
        lines.append("")

    out_path = Path(args.write_md)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}")

    if args.enforce and enforce_fail_reasons:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

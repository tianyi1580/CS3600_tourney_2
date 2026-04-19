#!/usr/bin/env python3
"""
Run a fixed bot2 test suite against a given bot1 using workflows/master_batch.py.
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute `.venv/bin/python workflows/master_batch.py <bot1> <bot2> "
            "--games 100 --quiet` for a user-provided bot2 suite."
        )
    )
    parser.add_argument("bot1", help="Bot under test (bot_first in master_batch.py).")
    parser.add_argument(
        "bot2_suite",
        nargs="+",
        help="One or more opponent bots. Example: <bot1> <bot2> <bot2> ...",
    )
    parser.add_argument(
        "--python",
        default=".venv/bin/python",
        help="Python interpreter used to launch master_batch.py (default: .venv/bin/python).",
    )
    parser.add_argument(
        "--games",
        type=int,
        default=100,
        help="Number of games per opponent (default: 100).",
    )
    parser.add_argument(
        "--output-dir",
        default="data/reports/master_batch_suite",
        help="Directory for aggregated suite output (default: data/reports/master_batch_suite).",
    )
    parser.add_argument("--parallel", action="store_true", help="Run matchups in parallel.")
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent matchup workers (default: 4).",
    )
    parser.add_argument(
        "--batch-parallel",
        action="store_true",
        help="Pass --parallel to each master_batch.py call.",
    )
    parser.add_argument(
        "--batch-workers",
        type=int,
        default=1,
        help="Number of workers per master_batch.py call (default: 1).",
    )
    return parser.parse_args()


def extract_summary(stdout: str) -> str:
    marker = "FINAL SUMMARY:"
    idx = stdout.find(marker)
    if idx == -1:
        return stdout.strip() if stdout.strip() else "<no output captured>"
    return stdout[idx:].strip()


def run_matchup(bot1: str, bot2: str, python_exec: Path, master_batch: Path, games: int, repo_root: Path, batch_parallel: bool, batch_workers: int):
    cmd = [
        str(python_exec),
        str(master_batch),
        bot1,
        bot2,
        "--games",
        str(games),
        "--quiet",
    ]
    if batch_parallel:
        cmd.append("--parallel")
        cmd.append("--workers")
        cmd.append(str(batch_workers))
        
    completed = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return bot2, cmd, completed


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    python_arg = Path(args.python).expanduser()
    # Keep venv interpreter path intact (do not resolve symlinks), or Python
    # may run outside the virtual environment.
    python_exec = python_arg if python_arg.is_absolute() else (repo_root / python_arg)
    master_batch = repo_root / "workflows" / "master_batch.py"
    agents_dir = repo_root / "3600-agents"
    output_dir = repo_root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"{args.bot1}_suite_{timestamp}.txt"

    sections: list[str] = []
    failures = 0

    # Preflight checks to fail fast on missing bot package names.
    available_bots = sorted(
        p.name for p in agents_dir.iterdir() if p.is_dir() and (p / "agent.py").is_file()
    )
    requested_bots = [args.bot1] + args.bot2_suite
    missing_bots = [name for name in requested_bots if name not in available_bots]
    if missing_bots:
        print("ERROR: Missing bot package(s):")
        for name in missing_bots:
            print(f"  - {name}")
        print("\nAvailable bots:")
        for name in available_bots:
            print(f"  - {name}")
        return 2

    print(f"Running suite for bot1={args.bot1}")
    print(f"Using python: {python_exec}")
    print(f"Writing report: {report_path}\n")

    matchup_results = []
    
    if args.parallel:
        print(f"Running {len(args.bot2_suite)} matchups in parallel with {args.workers} workers...")
        task = partial(
            run_matchup,
            bot1=args.bot1,
            python_exec=python_exec,
            master_batch=master_batch,
            games=args.games,
            repo_root=repo_root,
            batch_parallel=args.batch_parallel,
            batch_workers=args.batch_workers,
        )
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            future_to_bot2 = {executor.submit(task, bot2=b): b for b in args.bot2_suite}
            for i, future in enumerate(as_completed(future_to_bot2)):
                bot2, cmd, completed = future.result()
                matchup_results.append((bot2, cmd, completed))
                print(f"[{len(matchup_results)}/{len(args.bot2_suite)}] Finished {args.bot1} vs {bot2}")
    else:
        for idx, bot2 in enumerate(args.bot2_suite, start=1):
            print(f"[{idx}/{len(args.bot2_suite)}] {args.bot1} vs {bot2}")
            b2, cmd, completed = run_matchup(
                args.bot1, bot2, python_exec, master_batch, 
                args.games, repo_root, args.batch_parallel, args.batch_workers
            )
            matchup_results.append((b2, cmd, completed))
            summary = extract_summary(completed.stdout)
            print(summary)
            print()

    # Sort results by the original suite order for the report
    bot2_order = {name: i for i, name in enumerate(args.bot2_suite)}
    matchup_results.sort(key=lambda x: bot2_order[x[0]])

    for bot2, cmd, completed in matchup_results:
        summary = extract_summary(completed.stdout)
        section_lines = [
            "=" * 80,
            f"Matchup: {args.bot1} vs {bot2}",
            f"Command: {' '.join(cmd)}",
            f"Exit code: {completed.returncode}",
            "-" * 80,
            summary,
        ]

        if completed.returncode != 0:
            failures += 1
            err = completed.stderr.strip() or "<no stderr>"
            section_lines.extend(["-" * 80, "stderr:", err])
            if args.parallel:
                print(f"WARNING: Matchup {args.bot1} vs {bot2} failed with exit code {completed.returncode}")

        section = "\n".join(section_lines)
        sections.append(section)

    header = [
        f"Master Batch Suite Report",
        f"bot1: {args.bot1}",
        f"games_per_matchup: {args.games}",
        f"total_matchups: {len(args.bot2_suite)}",
        f"failures: {failures}",
        f"generated_at: {dt.datetime.now().isoformat(timespec='seconds')}",
        "",
    ]
    full_report = "\n".join(header + sections) + "\n"
    report_path.write_text(full_report, encoding="utf-8")

    print(f"Suite complete. Failures: {failures}/{len(args.bot2_suite)}")
    print(f"Report saved to: {report_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

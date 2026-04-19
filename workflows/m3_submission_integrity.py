#!/usr/bin/env python3
"""
Validate submission-packaging integrity for Yolanda M3 promotion:
- zip structure/size contract,
- deterministic fingerprint parity (source vs zipped bot),
- packaged-code smoke replay parity via `commentate()` build tag.
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / "3600-agents"
MAX_ZIP_BYTES = 200 * 1024 * 1024
BUILD_TAG_PATTERN = re.compile(r"build=([A-Za-z0-9:_-]+)")


@dataclass
class IntegrityResult:
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.failures.append(message)

    def note(self, message: str) -> None:
        self.notes.append(message)


def _build_zip_from_source(bot_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(bot_dir.rglob("*")):
            if not path.is_file():
                continue
            arcname = f"{bot_dir.name}/{path.relative_to(bot_dir).as_posix()}"
            zf.write(path, arcname=arcname)


def _zip_names(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as zf:
        return sorted(zf.namelist())


def _validate_zip_contract(zip_path: Path, bot_name: str, result: IntegrityResult) -> None:
    if not zip_path.exists():
        result.fail(f"missing_zip={zip_path}")
        return

    size = zip_path.stat().st_size
    result.note(f"zip_path={zip_path}")
    result.note(f"zip_size_bytes={size}")
    if size > MAX_ZIP_BYTES:
        result.fail(f"zip_size_exceeds_limit bytes={size} limit={MAX_ZIP_BYTES}")

    try:
        names = _zip_names(zip_path)
    except zipfile.BadZipFile:
        result.fail("zip_parse_error=bad_zip_file")
        return

    if not names:
        result.fail("zip_empty")
        return
    if any(name.startswith("/") for name in names):
        result.fail("zip_contains_absolute_path")
    if any(".." in Path(name).parts for name in names):
        result.fail("zip_contains_parent_traversal_path")

    top = {name.split("/", 1)[0] for name in names if name}
    if top != {bot_name}:
        result.fail(f"zip_top_level_mismatch top={sorted(top)} expected={[bot_name]}")

    required_agent = f"{bot_name}/agent.py"
    if required_agent not in names:
        result.fail(f"zip_missing_required_file={required_agent}")


def _extract_zip(zip_path: Path, target_dir: Path) -> Path:
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(target_dir)
    return target_dir


def _load_build_fingerprint(bot_name: str):
    sys.path.insert(0, str(AGENTS_DIR))
    module = __import__(
        f"{bot_name}.build_fingerprint",
        fromlist=["FINGERPRINT_SCHEMA_VERSION", "compute_build_fingerprint"],
    )
    return module.FINGERPRINT_SCHEMA_VERSION, module.compute_build_fingerprint


def _extract_build_tag(commentary: str) -> str | None:
    m = BUILD_TAG_PATTERN.search(commentary or "")
    return m.group(1) if m else None


def _run_packaged_commentary(bot_name: str, agents_root: Path, play_time: int) -> str:
    smoke_code = (
        "import importlib;"
        "import numpy as np;"
        "from game.board import Board;"
        "from game.enums import BOARD_SIZE;"
        f"agent_mod=importlib.import_module('{bot_name}.agent');"
        "PlayerAgent=agent_mod.PlayerAgent;"
        f"board=Board(time_to_play={play_time});"
        "board.player_worker.position=(3,3);"
        "board.opponent_worker.position=(4,4);"
        "agent=PlayerAgent(board, np.eye(BOARD_SIZE*BOARD_SIZE, dtype=np.float64), time_left=lambda:10.0);"
        "print(agent.commentate())"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT / 'engine'}:{agents_root}:{env.get('PYTHONPATH', '')}"
    proc = subprocess.run(
        [sys.executable, "-c", smoke_code],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30.0,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"constructor_commentate_smoke_failed returncode={proc.returncode} output={proc.stdout!r}")
    return proc.stdout.strip()


def _smoke_replay_and_compare(
    *,
    bot_name: str,
    source_agents_dir: Path,
    extracted_agents_dir: Path,
    expected_tag: str,
    smoke_games: int,
    play_time: int,
    result: IntegrityResult,
) -> None:
    if smoke_games <= 0:
        result.note("smoke_replay=skipped (smoke_games<=0)")
        return

    for run_idx in range(smoke_games):
        try:
            source_msg = _run_packaged_commentary(bot_name, source_agents_dir, play_time)
            zipped_msg = _run_packaged_commentary(bot_name, extracted_agents_dir, play_time)
        except Exception as exc:
            result.fail(f"smoke_run={run_idx} constructor_commentate_exception={exc}")
            continue

        source_tag = _extract_build_tag(source_msg)
        zipped_tag = _extract_build_tag(zipped_msg)
        result.note(f"smoke_run={run_idx} source_tag={source_tag} zipped_tag={zipped_tag}")
        if source_tag is None:
            result.fail(f"smoke_run={run_idx} missing_source_build_tag")
        if zipped_tag is None:
            result.fail(f"smoke_run={run_idx} missing_zipped_build_tag")
        if source_tag and source_tag != expected_tag:
            result.fail(f"smoke_run={run_idx} source_tag_mismatch got={source_tag} expected={expected_tag}")
        if zipped_tag and zipped_tag != expected_tag:
            result.fail(f"smoke_run={run_idx} zipped_tag_mismatch got={zipped_tag} expected={expected_tag}")


def _write_report(
    *,
    path: Path,
    bot_name: str,
    source_fingerprint: str,
    extracted_fingerprint: str,
    result: IntegrityResult,
) -> None:
    fail_count = len(result.failures)
    lines: list[str] = []
    lines.append("# M3 submission integrity report")
    lines.append("")
    lines.append("Generated by `workflows/m3_submission_integrity.py`.")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Bot: `{bot_name}`")
    lines.append(f"- Host platform: `{platform.system()}`")
    lines.append(f"- Source fingerprint: `{source_fingerprint}`")
    lines.append(f"- Extracted fingerprint: `{extracted_fingerprint}`")
    lines.append(f"- Failure count: `{fail_count}`")
    lines.append("")
    lines.append("## Findings")
    if result.failures:
        for message in result.failures:
            lines.append(f"- FAIL: {message}")
    else:
        lines.append("- PASS: zip contract, fingerprint parity, and smoke replay checks passed.")
    lines.append("")
    lines.append("## Evidence")
    for message in result.notes:
        lines.append(f"- {message}")
    lines.append("")
    lines.append("- Overall status: **PASS**" if fail_count == 0 else "- Overall status: **FAIL**")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bot-name", default="Yolanda")
    parser.add_argument("--zip-path", default="", help="Existing zip to validate. Empty => build temporary zip from source.")
    parser.add_argument("--smoke-games", type=int, default=2, help="Number of packaged-vs-source smoke games.")
    parser.add_argument("--play-time", type=int, default=240)
    parser.add_argument("--write-md", default="docs/m3_submission_integrity_report.md")
    parser.add_argument(
        "--enforce",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Exit non-zero when any integrity gate fails.",
    )
    args = parser.parse_args()

    bot_dir = AGENTS_DIR / args.bot_name
    if not bot_dir.exists():
        print(f"ERROR: missing bot directory: {bot_dir}")
        return 2

    schema_version, compute_build_fingerprint = _load_build_fingerprint(args.bot_name)
    result = IntegrityResult()
    source_hash = compute_build_fingerprint(bot_dir=bot_dir)
    expected_tag = f"{schema_version}:{source_hash}"
    result.note(f"expected_build_tag={expected_tag}")

    with tempfile.TemporaryDirectory(prefix="docs/m3_submission_integrity_") as tmp:
        tmp_dir = Path(tmp)
        if args.zip_path:
            zip_path = Path(args.zip_path).expanduser().resolve()
        else:
            zip_path = tmp_dir / f"{args.bot_name}.zip"
            _build_zip_from_source(bot_dir, zip_path)
            result.note("zip_origin=generated_from_local_source")

        _validate_zip_contract(zip_path, args.bot_name, result)

        extracted_root = _extract_zip(zip_path, tmp_dir / "unzipped")
        extracted_bot_dir = extracted_root / args.bot_name
        if not extracted_bot_dir.exists():
            result.fail(f"extracted_bot_dir_missing={extracted_bot_dir}")
            extracted_hash = ""
        else:
            extracted_hash = compute_build_fingerprint(bot_dir=extracted_bot_dir)
            if source_hash != extracted_hash:
                result.fail(
                    f"fingerprint_mismatch source={schema_version}:{source_hash} "
                    f"extracted={schema_version}:{extracted_hash}"
                )
            else:
                result.note("fingerprint_parity=PASS")

        if extracted_bot_dir.exists():
            _smoke_replay_and_compare(
                bot_name=args.bot_name,
                source_agents_dir=AGENTS_DIR,
                extracted_agents_dir=extracted_root,
                expected_tag=expected_tag,
                smoke_games=args.smoke_games,
                play_time=args.play_time,
                result=result,
            )

    report_path = Path(args.write_md)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    _write_report(
        path=report_path,
        bot_name=args.bot_name,
        source_fingerprint=f"{schema_version}:{source_hash}",
        extracted_fingerprint=f"{schema_version}:{extracted_hash}" if extracted_hash else "",
        result=result,
    )
    print(f"Wrote {report_path}")
    for line in result.notes:
        print(f"NOTE: {line}")
    for line in result.failures:
        print(f"FAIL: {line}")

    if args.enforce and result.failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

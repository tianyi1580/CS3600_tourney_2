"""Hyperopt pipeline for ``yolanda_prime_v4_7``.

Mirrors :mod:`workflows.yp2_hyperopt` but retargets the candidate agent, env
channel, and parameter schema to v3. The Stage-1 plan calls for tuning the
five-term leaf evaluator coefficients (tier A) first, and only later widening
to the time-manager and search-policy tiers; drivers select those tiers via
``PARAMETER_PROFILES["core" / "phase" / "extended"]`` from
``yolanda_prime_v4_7.infra.weights``.

Algorithm choice
----------------
The :mod:`scripts.optimize_yp2_weights` driver defaults to **CMA-ES** via
``pycma``. CMA-ES is the standard-bearer for noisy, low-to-moderate-dim
black-box continuous optimization: it adapts the step-size and the covariance
matrix across generations, handles scale mismatches between parameters, and
tolerates the per-game margin noise without oscillating. Falling back to a
simple (1+λ)-style GA is also supported for machines without pycma.

Ladder weighting (rebalanced for robustness)
--------------------------------------------
+--------------------------------+---------+--------+--------------------------+
|            opponent            | weight  | games  | rationale                |
+--------------------------------+---------+--------+--------------------------+
| yolanda_prime_v3               |   .30   |   70   | v3 regression anchor     |
| yolanda_prime_v1_2             |   .20   |   70   | prior stable v1.2        |
| Yolanda3_3                     |   .15   |   60   | field diversity          |
| Yolanda6                       |   .15   |   60   | field diversity          |
| yolanda_prime_v1_2Test         |   .20   |   70   | experimental v1.2 line   |
+--------------------------------+---------+--------+--------------------------+
Total: **330 games / candidate**. Weights sum to 1.0. Baseline weight lowered
from .35 → .30 and the two non-self peers lifted from .125 → .15 so the
optimizer cannot hill-climb by over-specializing against its own snapshot;
per-opponent SE on Yolanda3_3/6 drops from ~1.0 to ~0.87 margin points.

Fitness is the weighted sum of per-opponent avg-margin (same formula the yp12
pipeline uses); strict/regression/definitive checks are specialised for v3.
"""
from __future__ import annotations

import contextlib
import io
import json
import random
import sys
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = ROOT / "engine"
AGENTS_DIR = ROOT / "3600-agents"

if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

from game.enums import ResultArbiter, WinReason  # noqa: E402
from gameplay import play_game  # noqa: E402

from yolanda_prime_v4_7.infra.weights import (  # noqa: E402
    DEFAULTS,
    PARAMETER_PROFILES,
    bounds_for,
    clamp_weights,
    parameter_names,
    save_weights,
    serialize_weights,
    vector_to_weights,
    weights_to_vector,
)

# Generic infrastructure shared with yp12 (dataclasses, env helpers, winner
# normalisation, profile map). Re-exporting keeps the driver script simple.
from workflows.yp12_hyperopt import (  # noqa: E402
    FitnessResult,
    GameResult,
    GameTask,
    InfrastructureFailure,
    OpponentConfig,
    PROFILE_SETTINGS,
    SeriesResult,
    _CATASTROPHIC_REASONS,
    _absolute_ab_scores,
    _candidate_winner,
    _normalize_reason,
    _normalize_winner,
    _opponent_winner,
    _score_rate,
    _series_result,
    available_profiles,
    profile_settings,
    temporary_env,
)

# --------------------------------------------------------------------------
# v3-specific configuration.
# --------------------------------------------------------------------------

CANDIDATE_AGENT: str = "yolanda_prime_v4_7"
CANDIDATE_ENV_VAR: str = "YP4_WEIGHTS_JSON"
# We use yolanda_prime_v4_3 (minted from Stage-1 Core) as the regression anchor.
REGRESSION_OPPONENT: str = "yolanda_prime_v4_3"


DEFAULT_LADDER: tuple[OpponentConfig, ...] = (
    OpponentConfig("yolanda_prime_v3",          0.30, 21),
    OpponentConfig("yolanda_prime_v1_2",        0.20, 21),
    OpponentConfig("Yolanda3_3",                0.15, 18),
    OpponentConfig("Yolanda6",                  0.15, 18),
    OpponentConfig("yolanda_prime_v1_2Test",    0.20, 21),
)  # 99 games/candidate

HYPEROPT_LADDER: tuple[OpponentConfig, ...] = (
    OpponentConfig("yolanda_prime_v4_7_baseline", 0.40, 12),
    OpponentConfig("yolanda_prime_v4_3",          0.35, 10),
    OpponentConfig("yolanda_prime_v3",            0.25, 8),
)  # 30 games total across prioritized opponents for match-time efficiency

SMOKE_LADDER: tuple[OpponentConfig, ...] = (
    OpponentConfig("yolanda_prime_v3",          0.35, 2),
    OpponentConfig("yolanda_prime_v1_2",        0.20, 2),
    OpponentConfig("Yolanda3_3",                0.125, 2),
    OpponentConfig("Yolanda6",                  0.125, 2),
    OpponentConfig("yolanda_prime_v1_2Test",    0.20, 2),
)  # 10 games/candidate

STRICT_VALIDATION_OPPONENTS: tuple[str, ...] = (
    "yolanda_prime_v4_7_baseline",
    "yolanda_prime_v4_3",
    "yolanda_prime_v3",
)


def ladder_from_name(name: str) -> tuple[OpponentConfig, ...]:
    if name == "default":
        return DEFAULT_LADDER
    if name == "hyperopt":
        return HYPEROPT_LADDER
    if name == "smoke":
        return SMOKE_LADDER
    raise KeyError(f"unknown ladder preset: {name}")


@dataclass(frozen=True)
class MercyRuleConfig:
    enabled: bool = False
    min_games_before_prune: int = 10
    # Thresholds for average weighted margin relative to baseline
    floor_25: float = -5.0  # Kill significantly worse
    floor_50: float = -2.0  # Kill slightly worse
    # At 75%, if True, kill if candidate is significantly worse than the current generation leader
    prune_slow_leaders: bool = True
    leader_margin_delta: float = 3.0
    penalty: float = 50.0


def scale_ladder_games(
    ladder: Iterable[OpponentConfig],
    *,
    target_total_games: int | None,
) -> tuple[OpponentConfig, ...]:
    base = tuple(ladder)
    if target_total_games is None:
        return base
    if target_total_games <= 0:
        raise ValueError(f"target_total_games must be positive, got {target_total_games}")

    base_total = sum(max(0, opp.games) for opp in base)
    if base_total <= 0:
        return base
    if target_total_games == base_total:
        return base

    scaled: list[int] = []
    fractional: list[tuple[float, int]] = []
    running = 0
    for idx, opp in enumerate(base):
        if opp.games <= 0:
            scaled.append(0)
            continue
        raw = (opp.games * target_total_games) / base_total
        rounded = max(1, int(raw))
        scaled.append(rounded)
        running += rounded
        fractional.append((raw - int(raw), idx))

    delta = target_total_games - running
    if delta > 0:
        for _frac, idx in sorted(fractional, reverse=True):
            if delta <= 0:
                break
            scaled[idx] += 1
            delta -= 1
    elif delta < 0:
        for _frac, idx in sorted(fractional):
            if delta >= 0:
                break
            if scaled[idx] > 1:
                scaled[idx] -= 1
                delta += 1

    return tuple(
        OpponentConfig(opp.name, opp.weight, scaled[idx]) for idx, opp in enumerate(base)
    )


# --------------------------------------------------------------------------
# Game execution and evaluation.
# --------------------------------------------------------------------------


def run_single_game(task: GameTask) -> GameResult:
    if task.opponent_name == CANDIDATE_AGENT:
        raise ValueError(
            f"Candidate self-play evaluates the same build on both sides; "
            f"use a peer opponent instead of {CANDIDATE_AGENT!r}."
        )

    # Candidate weights flow through ``YP4_WEIGHTS_JSON``. Because v3's
    # regression anchor is simply ``yolanda_prime_v3`` (using its own
    # package weights), we do NOT inject a baseline-weights channel here.
    # This field is reserved for a future ``yolanda_prime_v4_3``.
    env_updates: dict[str, str | None] = {
        CANDIDATE_ENV_VAR: task.candidate_weights_json,
        "YP4_BASELINE_WEIGHTS_JSON": task.baseline_weights_json,
        "YP3_WEIGHTS_JSON": None,
        "YP12_WEIGHTS_JSON": None,
        "YP12_BASELINE_WEIGHTS_JSON": None,
    }

    random.seed(task.seed)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with temporary_env(env_updates):
        redirectors = contextlib.ExitStack()
        if task.quiet:
            redirectors.enter_context(contextlib.redirect_stdout(stdout))
            redirectors.enter_context(contextlib.redirect_stderr(stderr))
        with redirectors:
            player_a = CANDIDATE_AGENT if task.candidate_is_a else task.opponent_name
            player_b = task.opponent_name if task.candidate_is_a else CANDIDATE_AGENT
            last_failed_init: tuple[str, str] | None = None
            max_attempts = 2

            for attempt in range(1, max_attempts + 1):
                try:
                    board, _, _, _, message_a, message_b = play_game(
                        str(AGENTS_DIR),
                        str(AGENTS_DIR),
                        player_a,
                        player_b,
                        display_game=False,
                        delay=0,
                        clear_screen=False,
                        record=False,
                        limit_resources=task.limit_resources,
                        play_time_override=task.play_time,
                    )
                except Exception as exc:
                    raise InfrastructureFailure(
                        f"engine failure while running {player_a} vs {player_b} (seed={task.seed})"
                    ) from exc

                winner = _normalize_winner(getattr(board, "winner", ResultArbiter.ERROR))
                win_reason = _normalize_reason(getattr(board, "win_reason", WinReason.CODE_CRASH))
                if win_reason != WinReason.FAILED_INIT:
                    break

                last_failed_init = (message_a, message_b)
                if attempt == max_attempts:
                    msg_a, msg_b = last_failed_init
                    raise InfrastructureFailure(
                        f"FAILED_INIT in {player_a} vs {player_b} (seed={task.seed}) "
                        f"after {max_attempts} attempts A={msg_a!r} B={msg_b!r}"
                    )

            if winner == ResultArbiter.ERROR:
                raise InfrastructureFailure(
                    f"engine returned ERROR winner in {player_a} vs {player_b} (seed={task.seed}) "
                    f"reason={win_reason.name}"
                )

    score_a, score_b = _absolute_ab_scores(board)
    if task.candidate_is_a:
        candidate_score, opponent_score = score_a, score_b
    else:
        candidate_score, opponent_score = score_b, score_a

    catastrophic_loss = (
        winner == _opponent_winner(task.candidate_is_a)
        and win_reason in _CATASTROPHIC_REASONS
    )
    margin = float(
        task.catastrophic_penalty if catastrophic_loss
        else candidate_score - opponent_score
    )

    return GameResult(
        seed=task.seed,
        opponent_name=task.opponent_name,
        candidate_is_a=task.candidate_is_a,
        margin=margin,
        win_reason=win_reason.name,
        winner=winner.name,
        candidate_score=int(candidate_score),
        opponent_score=int(opponent_score),
        timed_out=catastrophic_loss and win_reason == WinReason.TIMEOUT,
        invalid_turn=catastrophic_loss and win_reason == WinReason.INVALID_TURN,
        crashed=catastrophic_loss and win_reason == WinReason.CODE_CRASH,
        memory_error=catastrophic_loss and win_reason == WinReason.MEMORY_ERROR,
        failed_init=catastrophic_loss and win_reason == WinReason.FAILED_INIT,
        catastrophic_loss=catastrophic_loss,
    )


def evaluate_series(
    weights: Mapping[str, float],
    opponent_name: str,
    *,
    games: int,
    seed_start: int = 42,
    profile: str = "tuning",
    workers: int = 1,
    catastrophic_penalty: float = -50.0,
    baseline_weights: Mapping[str, float] | None = None,
    quiet: bool = True,
    pool_override: ProcessPoolExecutor | None = None,
) -> SeriesResult:
    play_time, limit_resources = profile_settings(profile)
    clamped_weights = clamp_weights(weights)
    candidate_json = serialize_weights(clamped_weights)
    baseline_json = serialize_weights(baseline_weights) if baseline_weights is not None else None
    tasks = [
        GameTask(
            candidate_weights_json=candidate_json,
            baseline_weights_json=baseline_json,
            opponent_name=opponent_name,
            seed=seed_start + game_idx,
            candidate_is_a=(game_idx % 2 == 0),
            play_time=play_time,
            limit_resources=limit_resources,
            catastrophic_penalty=catastrophic_penalty,
            quiet=quiet,
        )
        for game_idx in range(games)
    ]

    if pool_override is not None:
        results = list(pool_override.map(run_single_game, tasks))
        return _series_result(opponent_name, results)

    if workers <= 1:
        results = [run_single_game(task) for task in tasks]
        return _series_result(opponent_name, results)

    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run_single_game, tasks))
    return _series_result(opponent_name, results)


def evaluate_fitness(
    weights: Mapping[str, float],
    *,
    ladder: Iterable[OpponentConfig] = HYPEROPT_LADDER,
    profile: str = "tuning",
    seed_start: int = 42,
    workers_per_series: int = 1,
    catastrophic_penalty: float = -50.0,
    baseline_weights: Mapping[str, float] | None = None,
    quiet: bool = True,
    pool_override: ProcessPoolExecutor | None = None,
) -> FitnessResult:
    clamped = clamp_weights(weights)
    fitness = 0.0
    ladder_results: list[dict[str, object]] = []

    for offset, opponent in enumerate(ladder):
        series = evaluate_series(
            clamped,
            opponent.name,
            games=opponent.games,
            seed_start=seed_start + 10_000 * offset,
            profile=profile,
            workers=workers_per_series,
            catastrophic_penalty=catastrophic_penalty,
            baseline_weights=baseline_weights,
            quiet=quiet,
            pool_override=pool_override,
        )
        fitness += opponent.weight * series.avg_margin
        ladder_results.append(
            {
                "opponent": opponent.name,
                "weight": opponent.weight,
                **asdict(series),
            }
        )

    return FitnessResult(
        fitness=fitness,
        profile=profile,
        ladder=ladder_results,
        weights=clamped,
    )


def evaluate_generation_flat(
    candidates: Sequence[Mapping[str, float]],
    *,
    ladder: Iterable[OpponentConfig] = HYPEROPT_LADDER,
    profile: str = "tuning",
    seed_start: int = 42,
    workers: int = 1,
    catastrophic_penalty: float = -50.0,
    baseline_weights: Mapping[str, float] | None = None,
    quiet: bool = True,
    mercy: MercyRuleConfig | None = None,
    checkpoint_dir: Path | None = None,
    pool_override: ProcessPoolExecutor | None = None,
) -> list[dict[str, object]]:
    """Evaluates a population of candidates with multi-stage early pruning and checkpointing.

    If ``checkpoint_dir`` is provided, partial results are saved to a file after each
    stage to support mid-generation resumption.

    If ``pool_override`` is provided, that executor is used instead of creating a new one.
    """
    if not candidates:
        return []
    mercy_cfg = mercy or MercyRuleConfig(enabled=False)
    clamped_candidates = [clamp_weights(candidate) for candidate in candidates]
    candidate_json = [serialize_weights(weights) for weights in clamped_candidates]
    baseline_json = serialize_weights(baseline_weights) if baseline_weights is not None else None
    ladder_tuple = tuple(ladder)
    play_time, limit_resources = profile_settings(profile)

    # Multi-stage task execution
    stages = [0.25, 0.50, 0.75, 1.0]
    task_map: dict[float, list[tuple[int, int, int, GameTask]]] = {s: [] for s in stages}

    # Accumulator shape: [candidate][opponent] -> series counters.
    accum: list[list[dict[str, object]]] = []
    for _cand_idx in range(len(clamped_candidates)):
        rows: list[dict[str, object]] = []
        for opp in ladder_tuple:
            rows.append(
                {
                    "opponent_name": opp.name,
                    "weight": opp.weight,
                    "games": 0,
                    "wins": 0,
                    "losses": 0,
                    "ties": 0,
                    "timeouts": 0,
                    "invalid_turns": 0,
                    "crashes": 0,
                    "memory_errors": 0,
                    "failed_inits": 0,
                    "catastrophic_losses": 0,
                    "margin_sum": 0.0,
                    "margins": [],
                }
            )
        accum.append(rows)

    evaluated_games: list[int] = [0] * len(clamped_candidates)
    total_planned_games: list[int] = [sum(opp.games for opp in ladder_tuple)] * len(clamped_candidates)
    pruned: list[bool] = [False] * len(clamped_candidates)
    current_weighted_margin: list[float] = [0.0] * len(clamped_candidates)

    def _task_for(c_idx: int, o_idx: int, g_idx: int) -> GameTask:
        opp = ladder_tuple[o_idx]
        is_a = (g_idx % 2 == 0)
        return GameTask(
            candidate_weights_json=candidate_json[c_idx],
            opponent_name=opp.name,
            candidate_is_a=is_a,
            play_time=play_time,
            limit_resources=limit_resources,
            seed=seed_start + (c_idx * 1_000_000) + (o_idx * 10_000) + g_idx,
            baseline_weights_json=baseline_json,
            catastrophic_penalty=catastrophic_penalty,
            quiet=quiet,
        )

    max_ladder_games = max(opp.games for opp in ladder_tuple) if ladder_tuple else 0
    for g_idx in range(max_ladder_games):
        for o_idx, opp in enumerate(ladder_tuple):
            if g_idx >= opp.games:
                continue
            for c_idx in range(len(clamped_candidates)):
                fraction = (g_idx + 1) / opp.games
                task = (c_idx, o_idx, g_idx, _task_for(c_idx, o_idx, g_idx))
                if fraction <= 0.25:
                    task_map[0.25].append(task)
                elif fraction <= 0.50:
                    task_map[0.50].append(task)
                elif fraction <= 0.75:
                    task_map[0.75].append(task)
                else:
                    task_map[1.0].append(task)

    def _apply_result(c_idx: int, o_idx: int, result: GameResult) -> None:
        row = accum[c_idx][o_idx]
        row["games"] = int(row["games"]) + 1
        row["margin_sum"] = float(row["margin_sum"]) + float(result.margin)
        row["margins"].append(float(result.margin))
        if result.winner == "PLAYER_A" and result.candidate_is_a:
            row["wins"] = int(row["wins"]) + 1
        elif result.winner == "PLAYER_B" and not result.candidate_is_a:
            row["wins"] = int(row["wins"]) + 1
        elif result.winner == "NONE":
            row["ties"] = int(row["ties"]) + 1
        else:
            row["losses"] = int(row["losses"]) + 1
        if result.timed_out:
            row["timeouts"] = int(row["timeouts"]) + 1
        if result.invalid_turn:
            row["invalid_turns"] = int(row["invalid_turns"]) + 1
        if result.crashed:
            row["crashes"] = int(row["crashes"]) + 1
        if result.memory_error:
            row["memory_errors"] = int(row["memory_errors"]) + 1
        if result.failed_init:
            row["failed_inits"] = int(row["failed_inits"]) + 1
        if result.catastrophic_loss:
            row["catastrophic_losses"] = int(row["catastrophic_losses"]) + 1
        evaluated_games[c_idx] += 1

    def _recompute_weighted(c_idx: int) -> float:
        value = 0.0
        for o_idx, opp in enumerate(ladder_tuple):
            played = int(accum[c_idx][o_idx]["games"])
            avg = (float(accum[c_idx][o_idx]["margin_sum"]) / played) if played > 0 else 0.0
            value += opp.weight * avg
        current_weighted_margin[c_idx] = value
        return value

    # Load from checkpoint if it exists
    checkpoint_file = checkpoint_dir / "flattened_progress.json" if checkpoint_dir else None
    if checkpoint_file and checkpoint_file.exists():
        try:
            data = json.loads(checkpoint_file.read_text())
            # Ensure the checkpoint matches our current population and seed
            if data.get("seed_start") == seed_start and len(data.get("accum", [])) == len(clamped_candidates):
                accum = data["accum"]
                
                # Checkpoints may be saved as lists (JSON arrays) or dicts.
                # Always convert back to lists for stable indexing.
                raw_pruned = data.get("pruned", [])
                if isinstance(raw_pruned, dict):
                    pruned = [False] * len(clamped_candidates)
                    for k, v in raw_pruned.items():
                        pruned[int(k)] = bool(v)
                else:
                    pruned = [bool(v) for v in raw_pruned]
                
                raw_games = data.get("evaluated_games", [])
                if isinstance(raw_games, dict):
                    evaluated_games = [0] * len(clamped_candidates)
                    for k, v in raw_games.items():
                        evaluated_games[int(k)] = int(v)
                else:
                    evaluated_games = [int(v) for v in raw_games]

                for s in stages:
                    new_tasks = []
                    for c_idx, o_idx, g_idx, task in task_map[s]:
                        if g_idx >= accum[c_idx][o_idx]["games"]:
                            new_tasks.append((c_idx, o_idx, g_idx, task))
                    task_map[s] = new_tasks
                print(f"Resuming evaluate_generation_flat from stage checkpoint (evaluated_games={sum(evaluated_games)})", flush=True)
        except Exception as e:
            print(f"Failed to load stage-level checkpoint: {e}", flush=True)

    def _run_stages(pool):
        for stage in stages:
            tasks = task_map[stage]
            if tasks:
                pending: dict[object, tuple[int, int]] = {}
                task_iter = iter(tasks)
                while True:
                    while len(pending) < workers:
                        try:
                            c_idx, o_idx, _g_idx, task = next(task_iter)
                        except StopIteration:
                            break
                        if pruned[c_idx]:
                            continue
                        fut = pool.submit(run_single_game, task)
                        pending[fut] = (c_idx, o_idx)
                    if not pending:
                        break
                    done, _ = wait(set(pending.keys()), return_when=FIRST_COMPLETED)
                    for fut in done:
                        c_idx, o_idx = pending.pop(fut)
                        try:
                            _apply_result(c_idx, o_idx, fut.result())
                        except Exception as e:
                            print(f"  [ERROR] Task for candidate {c_idx} vs {o_idx} failed: {e}", flush=True)
                            # Provide a sentinel failed result to avoid missing entries
                            sentinel = GameResult(
                                seed=-1, opponent_name=ladder_tuple[o_idx].name, 
                                candidate_is_a=False, margin=mercy_cfg.floor_25,
                                win_reason="TASK_CRASH", winner="ERROR",
                                candidate_score=0, opponent_score=0,
                                timed_out=False, invalid_turn=False, crashed=True,
                                memory_error=False, failed_init=False, catastrophic_loss=True
                            )
                            _apply_result(c_idx, o_idx, sentinel)

            # Pruning check at the end of each stage
            if mercy_cfg.enabled:
                leader_score = -999.0
                for c_idx in range(len(clamped_candidates)):
                    if evaluated_games[c_idx] > 0:
                        leader_score = max(leader_score, _recompute_weighted(c_idx))
                
                for c_idx in range(len(clamped_candidates)):
                    if pruned[c_idx]: continue
                    if evaluated_games[c_idx] < mercy_cfg.min_games_before_prune:
                        continue
                        
                    score = _recompute_weighted(c_idx)
                    if stage == 0.25 and score < mercy_cfg.floor_25:
                        pruned[c_idx] = True
                    elif stage == 0.50 and score < mercy_cfg.floor_50:
                        pruned[c_idx] = True
                    elif stage == 0.75 and mercy_cfg.prune_slow_leaders:
                        if score < (leader_score - mercy_cfg.leader_margin_delta):
                            pruned[c_idx] = True
            
            # Save stage-level checkpoint
            if checkpoint_file:
                try:
                    checkpoint_file.write_text(json.dumps({
                        "seed_start": seed_start,
                        "accum": accum,
                        "pruned": pruned,
                        "evaluated_games": evaluated_games,
                    }))
                except Exception as e:
                    print(f"Failed to save stage-level checkpoint: {e}", flush=True)

    # Execute stages sequentially with pruning checks
    if pool_override is not None:
        _run_stages(pool_override)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            _run_stages(pool)

    if checkpoint_file and checkpoint_file.exists():
        checkpoint_file.unlink()

    rows: list[dict[str, object]] = []
    for c_idx, clamped in enumerate(clamped_candidates):
        fitness = 0.0
        ladder_rows: list[dict[str, object]] = []
        for o_idx, opp in enumerate(ladder_tuple):
            row = accum[c_idx][o_idx]
            games = int(row["games"])
            avg_margin = (float(row["margin_sum"]) / games) if games > 0 else 0.0
            fitness += opp.weight * avg_margin
            ladder_rows.append(
                {
                    "opponent": opp.name,
                    "weight": opp.weight,
                    "opponent_name": opp.name,
                    "avg_margin": avg_margin,
                    "games": games,
                    "wins": int(row["wins"]),
                    "losses": int(row["losses"]),
                    "ties": int(row["ties"]),
                    "timeouts": int(row["timeouts"]),
                    "invalid_turns": int(row["invalid_turns"]),
                    "crashes": int(row["crashes"]),
                    "memory_errors": int(row["memory_errors"]),
                    "failed_inits": int(row["failed_inits"]),
                    "catastrophic_losses": int(row["catastrophic_losses"]),
                    "margins": row["margins"],
                }
            )
        if pruned[c_idx]:
            fitness -= mercy_cfg.penalty
        rows.append(
            {
                "fitness": fitness,
                "profile": profile,
                "ladder": ladder_rows,
                "weights": clamped,
                "pruned": pruned[c_idx],
                "evaluated_games": evaluated_games[c_idx],
                "planned_games": total_planned_games[c_idx],
                "effective_games_ratio": (
                    float(evaluated_games[c_idx]) / float(total_planned_games[c_idx])
                    if total_planned_games[c_idx] > 0 else 0.0
                ),
            }
        )
    return rows


# --------------------------------------------------------------------------
# Post-run validation gates.
# --------------------------------------------------------------------------


def strict_mode_validation(
    weights: Mapping[str, float],
    *,
    games_per_opponent: int = 5,
    seed_start: int = 100_000,
    workers: int = 1,
    quiet: bool = True,
    pool_override: ProcessPoolExecutor | None = None,
) -> tuple[bool, list[dict[str, object]]]:
    """Runs high-time-budget games across several opponents to check for crashes or major regressions."""
    play_time, limit_resources = profile_settings("strict")
    clamped_weights = clamp_weights(weights)
    candidate_json = serialize_weights(clamped_weights)
    
    tasks: list[tuple[str, GameTask]] = []
    for idx, opponent_name in enumerate(STRICT_VALIDATION_OPPONENTS):
        for g_idx in range(games_per_opponent):
            task = GameTask(
                candidate_weights_json=candidate_json,
                opponent_name=opponent_name,
                seed=seed_start + 5_000 * idx + g_idx,
                candidate_is_a=(g_idx % 2 == 0),
                play_time=play_time,
                limit_resources=limit_resources,
                catastrophic_penalty=-50.0,
                quiet=quiet,
            )
            tasks.append((opponent_name, task))

    if pool_override is not None:
        futures = {pool_override.submit(run_single_game, t): opp for opp, t in tasks}
        game_results = [(futures[f], f.result()) for f in futures]
    elif workers <= 1:
        game_results = [(opp, run_single_game(t)) for opp, t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run_single_game, t): opp for opp, t in tasks}
            game_results = [(futures[f], f.result()) for f in futures]

    # Aggregate by opponent
    results_by_opp: dict[str, list[GameResult]] = {opp: [] for opp in STRICT_VALIDATION_OPPONENTS}
    for opp, res in game_results:
        results_by_opp[opp].append(res)
    
    details: list[dict[str, object]] = []
    passed = True
    for opponent_name in STRICT_VALIDATION_OPPONENTS:
        series = _series_result(opponent_name, results_by_opp[opponent_name])
        details.append(asdict(series))
        if series.catastrophic_losses > 0:
            passed = False
    return passed, details


def regression_check(
    new_weights: Mapping[str, float],
    *,
    baseline_weights: Mapping[str, float] | None = None,
    games: int = 40,
    required_score_rate: float = 0.55,
    seed_start: int = 200_000,
    profile: str = "tuning",
    workers: int = 1,
    quiet: bool = True,
    pool_override: ProcessPoolExecutor | None = None,
) -> tuple[bool, dict[str, object]]:
    """Candidate weights must beat the frozen v4_3 baseline."""
    series = evaluate_series(
        new_weights,
        REGRESSION_OPPONENT,
        games=games,
        seed_start=seed_start,
        profile=profile,
        baseline_weights=baseline_weights,
        workers=workers,
        quiet=quiet,
        pool_override=pool_override,
    )
    score_rate = _score_rate(series)
    details = asdict(series)
    details["score_rate"] = score_rate
    details["required_score_rate"] = required_score_rate
    details["opponent_name"] = REGRESSION_OPPONENT
    return (
        score_rate >= required_score_rate and series.catastrophic_losses == 0,
        details,
    )


def definitive_improvement_check(
    new_weights: Mapping[str, float],
    *,
    baseline_weights: Mapping[str, float] | None = None,
    opponents: Sequence[str] = (
        "yolanda_prime_v4_7_baseline",
        "yolanda_prime_v4_3",
        "yolanda_prime_v3",
    ),
    games_per_opponent: int = 200,
    required_score_rate: float = 0.52,
    require_positive_margin: bool = True,
    seed_start: int = 300_000,
    profile: str = "tuning",
    workers: int = 1,
    quiet: bool = False,
    pool_override: ProcessPoolExecutor | None = None,
) -> tuple[bool, dict[str, object]]:
    """Strictly parallel evaluation against multiple baseline snapshots."""
    play_time, limit_resources = profile_settings(profile)
    clamped_weights = clamp_weights(new_weights)
    candidate_json = serialize_weights(clamped_weights)
    baseline_json = serialize_weights(baseline_weights) if baseline_weights is not None else None

    tasks: list[tuple[str, GameTask]] = []
    for idx, opponent_name in enumerate(opponents):
        for g_idx in range(games_per_opponent):
            task = GameTask(
                candidate_weights_json=candidate_json,
                baseline_weights_json=baseline_json,
                opponent_name=opponent_name,
                seed=seed_start + 10_000 * idx + g_idx,
                candidate_is_a=(g_idx % 2 == 0),
                play_time=play_time,
                limit_resources=limit_resources,
                catastrophic_penalty=-50.0,
                quiet=quiet,
            )
            tasks.append((opponent_name, task))

    if pool_override is not None:
        futures = {pool_override.submit(run_single_game, t): opp for opp, t in tasks}
        game_results = [(futures[f], f.result()) for f in futures]
    elif workers <= 1:
        game_results = [(opp, run_single_game(t)) for opp, t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run_single_game, t): opp for opp, t in tasks}
            game_results = [(futures[f], f.result()) for f in futures]

    # Aggregate and check requirements
    results_by_opp: dict[str, list[GameResult]] = {opp: [] for opp in opponents}
    for opp, res in game_results:
        results_by_opp[opp].append(res)

    rows: list[dict[str, object]] = []
    passed = True
    for opponent in opponents:
        series = _series_result(opponent, results_by_opp[opponent])
        score_rate = _score_rate(series)
        row = asdict(series)
        row["score_rate"] = score_rate
        row["required_score_rate"] = required_score_rate
        row["require_positive_margin"] = require_positive_margin
        rows.append(row)
        
        if series.catastrophic_losses > 0:
            passed = False
        if score_rate < required_score_rate:
            passed = False
        if require_positive_margin and series.avg_margin <= 0.0:
            passed = False

    details: dict[str, object] = {
        "opponents": list(opponents),
        "games_per_opponent": games_per_opponent,
        "required_score_rate": required_score_rate,
        "require_positive_margin": require_positive_margin,
        "rows": rows,
    }
    return passed, details


def write_best_weights(path: Path, weights: Mapping[str, float], *, profile: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    save_weights(path, weights, profile=profile)


__all__ = [
    "AGENTS_DIR",
    "CANDIDATE_AGENT",
    "CANDIDATE_ENV_VAR",
    "DEFAULTS",
    "DEFAULT_LADDER",
    "HYPEROPT_LADDER",
    "FitnessResult",
    "GameResult",
    "GameTask",
    "InfrastructureFailure",
    "OpponentConfig",
    "PARAMETER_PROFILES",
    "PROFILE_SETTINGS",
    "REGRESSION_OPPONENT",
    "SMOKE_LADDER",
    "STRICT_VALIDATION_OPPONENTS",
    "SeriesResult",
    "available_profiles",
    "bounds_for",
    "clamp_weights",
    "definitive_improvement_check",
    "MercyRuleConfig",
    "evaluate_fitness",
    "evaluate_generation_flat",
    "evaluate_series",
    "ladder_from_name",
    "parameter_names",
    "profile_settings",
    "regression_check",
    "run_single_game",
    "serialize_weights",
    "scale_ladder_games",
    "strict_mode_validation",
    "vector_to_weights",
    "weights_to_vector",
    "write_best_weights",
]

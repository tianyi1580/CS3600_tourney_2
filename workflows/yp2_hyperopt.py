"""Hyperopt pipeline for ``yolanda_prime_v2``.

Design mirrors :mod:`workflows.yp12_hyperopt` but retargets the candidate
agent, env channel, and opponent ladder for v2. We share all generic
infrastructure (dataclasses, helpers, env gymnastics) with the yp12 module to
avoid drift between the two pipelines; only the v2-specific policy surface is
duplicated here.

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
| yolanda_prime_v2_baseline      |   .30   |   70   | frozen v2 package weights|
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
pipeline uses); strict/regression/definitive checks are specialised for v2.
"""
from __future__ import annotations

import contextlib
import io
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

# yp2 shares the same weight schema (``core``/``phase``/``extended`` profiles,
# bounds, clamping, serialization) as yp12 — the policy signature is identical
# at the parameter layer. If v2 ever introduces new weights, import from
# ``yolanda_prime_v2.infra.weights`` instead.
from yolanda_prime_v2.infra.weights import (  # noqa: E402
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
# v2-specific configuration.
# --------------------------------------------------------------------------

CANDIDATE_AGENT: str = "yolanda_prime_v2"
CANDIDATE_ENV_VAR: str = "YP2_WEIGHTS_JSON"
# Frozen package-weight snapshot; regression gate ensures we do not ship worse
# than the baseline v2 line.
REGRESSION_OPPONENT: str = "yolanda_prime_v2_baseline"


DEFAULT_LADDER: tuple[OpponentConfig, ...] = (
    # Smaller default ladder for cheap evaluations / interactive use (~same
    # relative weights as HYPEROPT_LADDER, fewer games).
    OpponentConfig("yolanda_prime_v2_baseline", 0.30, 21),
    OpponentConfig("yolanda_prime_v1_2",        0.20, 21),
    OpponentConfig("Yolanda3_3",                0.15, 18),
    OpponentConfig("Yolanda6",                  0.15, 18),
    OpponentConfig("yolanda_prime_v1_2Test",    0.20, 21),
)  # 99 games/candidate

HYPEROPT_LADDER: tuple[OpponentConfig, ...] = (
    OpponentConfig("yolanda_prime_v2_baseline", 0.30, 70),
    OpponentConfig("yolanda_prime_v1_2",        0.20, 70),
    OpponentConfig("Yolanda3_3",                0.15, 60),
    OpponentConfig("Yolanda6",                  0.15, 60),
    OpponentConfig("yolanda_prime_v1_2Test",    0.20, 70),
)  # 330 games/candidate

SMOKE_LADDER: tuple[OpponentConfig, ...] = (
    # Tiny ladder for pipeline plumbing validation / CI smoke tests.
    OpponentConfig("yolanda_prime_v2_baseline", 0.35, 2),
    OpponentConfig("yolanda_prime_v1_2",        0.20, 2),
    OpponentConfig("Yolanda3_3",                0.125, 2),
    OpponentConfig("Yolanda6",                  0.125, 2),
    OpponentConfig("yolanda_prime_v1_2Test",    0.20, 2),
)  # 10 games/candidate

STRICT_VALIDATION_OPPONENTS: tuple[str, ...] = (
    # Anchor baseline + two 0.20 yolanda-family peers + a non-family peer
    # (Yolanda3_3) so the strict gate catches crashes against diverse-field
    # opponents, not just against other Yolanda variants.
    "yolanda_prime_v2_baseline",
    "yolanda_prime_v1_2",
    "yolanda_prime_v1_2Test",
    "Yolanda3_3",
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
    stage_a_fraction: float = 0.5
    min_games_before_prune: int = 120
    fixed_margin_floor: float = -5.0
    penalty: float = 1.0


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

    # Candidate weights flow through ``YP2_WEIGHTS_JSON``. Opponent
    # ``yolanda_prime_v2_baseline`` reads ``YP2_BASELINE_WEIGHTS_JSON`` (see
    # its agent wrapper) so it never picks up the candidate vector. If the
    # caller passed ``baseline_weights`` (regression gate / definitive check),
    # route it into the v2 baseline channel so ``yolanda_prime_v2_baseline``
    # evaluates the supplied snapshot instead of its frozen package weights.
    env_updates: dict[str, str | None] = {
        CANDIDATE_ENV_VAR: task.candidate_weights_json,
    }
    if task.baseline_weights_json is not None:
        env_updates["YP2_BASELINE_WEIGHTS_JSON"] = task.baseline_weights_json

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
) -> list[dict[str, object]]:
    if not candidates:
        return []
    mercy_cfg = mercy or MercyRuleConfig()
    clamped_candidates = [clamp_weights(candidate) for candidate in candidates]
    candidate_json = [serialize_weights(weights) for weights in clamped_candidates]
    baseline_json = serialize_weights(baseline_weights) if baseline_weights is not None else None
    ladder_tuple = tuple(ladder)
    play_time, limit_resources = profile_settings(profile)

    stage_a_games: dict[int, int] = {}
    for opp_idx, opp in enumerate(ladder_tuple):
        stage = int(round(opp.games * mercy_cfg.stage_a_fraction))
        stage_a_games[opp_idx] = min(opp.games, max(0, stage))

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

    def _candidate_seed_base(c_idx: int) -> int:
        return seed_start + (c_idx * 1_000_000)

    def _task_for(c_idx: int, o_idx: int, g_idx: int) -> GameTask:
        return GameTask(
            candidate_weights_json=candidate_json[c_idx],
            baseline_weights_json=baseline_json,
            opponent_name=ladder_tuple[o_idx].name,
            seed=_candidate_seed_base(c_idx) + (o_idx * 10_000) + g_idx,
            candidate_is_a=(g_idx % 2 == 0),
            play_time=play_time,
            limit_resources=limit_resources,
            catastrophic_penalty=catastrophic_penalty,
            quiet=quiet,
        )

    stage_a_tasks: list[tuple[int, int, int, GameTask]] = []
    stage_b_tasks: list[tuple[int, int, int, GameTask]] = []
    for c_idx in range(len(clamped_candidates)):
        for o_idx, opp in enumerate(ladder_tuple):
            split = stage_a_games[o_idx]
            for g_idx in range(opp.games):
                task = (c_idx, o_idx, g_idx, _task_for(c_idx, o_idx, g_idx))
                if g_idx < split:
                    stage_a_tasks.append(task)
                else:
                    stage_b_tasks.append(task)

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

    def _run_tasks(tasks: list[tuple[int, int, int, GameTask]]) -> None:
        if not tasks:
            return
        if workers <= 1:
            for c_idx, o_idx, _g_idx, task in tasks:
                if pruned[c_idx]:
                    continue
                _apply_result(c_idx, o_idx, run_single_game(task))
            return

        with ProcessPoolExecutor(max_workers=workers) as pool:
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
                    _apply_result(c_idx, o_idx, fut.result())

    _run_tasks(stage_a_tasks)

    if mercy_cfg.enabled:
        for c_idx in range(len(clamped_candidates)):
            if evaluated_games[c_idx] < mercy_cfg.min_games_before_prune:
                continue
            score = _recompute_weighted(c_idx)
            if score < mercy_cfg.fixed_margin_floor:
                pruned[c_idx] = True

    _run_tasks(stage_b_tasks)

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
    quiet: bool = True,
) -> tuple[bool, list[dict[str, object]]]:
    details: list[dict[str, object]] = []
    passed = True
    for idx, opponent_name in enumerate(STRICT_VALIDATION_OPPONENTS):
        series = evaluate_series(
            weights,
            opponent_name,
            games=games_per_opponent,
            seed_start=seed_start + 5_000 * idx,
            profile="strict",
            catastrophic_penalty=-50.0,
            quiet=quiet,
        )
        details.append(asdict(series))
        if series.catastrophic_losses > 0:
            passed = False
    return passed, details


def regression_check(
    new_weights: Mapping[str, float],
    *,
    baseline_weights: Mapping[str, float] | None = None,
    games: int = 50,
    required_score_rate: float = 0.55,
    seed_start: int = 200_000,
    profile: str = "tuning",
    quiet: bool = True,
) -> tuple[bool, dict[str, object]]:
    """Candidate weights must beat the frozen v2 baseline (package snapshot)."""
    series = evaluate_series(
        new_weights,
        REGRESSION_OPPONENT,
        games=games,
        seed_start=seed_start,
        profile=profile,
        baseline_weights=baseline_weights,
        quiet=quiet,
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
        "yolanda_prime_v2_baseline",
        "yolanda_prime_v1_2",
        "Yolanda3_3",
        "Yolanda6",
        "yolanda_prime_v1_2Test",
    ),
    games_per_opponent: int = 200,
    required_score_rate: float = 0.52,
    require_positive_margin: bool = True,
    seed_start: int = 500_000,
    profile: str = "tuning",
    quiet: bool = True,
) -> tuple[bool, dict[str, object]]:
    """Beats each named opponent on BOTH win-rate proxy and positive margin."""
    rows: list[dict[str, object]] = []
    passed = True
    for idx, opponent in enumerate(opponents):
        try:
            series = evaluate_series(
                new_weights,
                opponent,
                games=games_per_opponent,
                seed_start=seed_start + 10_000 * idx,
                profile=profile,
                baseline_weights=baseline_weights,
                quiet=quiet,
            )
        except InfrastructureFailure as exc:
            passed = False
            rows.append(
                {
                    "opponent_name": opponent,
                    "games": games_per_opponent,
                    "infrastructure_failure": True,
                    "error": str(exc),
                    "score_rate": 0.0,
                    "required_score_rate": required_score_rate,
                    "require_positive_margin": require_positive_margin,
                    "avg_margin": float("-inf"),
                    "catastrophic_losses": games_per_opponent,
                }
            )
            continue

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

from __future__ import annotations

import contextlib
import io
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor
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
from yolanda_prime_v1_2.infra.weights import (  # noqa: E402
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


class InfrastructureFailure(RuntimeError):
    """Raised when the evaluation harness fails and fitness numbers would be garbage."""


@dataclass(frozen=True)
class OpponentConfig:
    name: str
    weight: float
    games: int


@dataclass(frozen=True)
class GameTask:
    candidate_weights_json: str
    opponent_name: str
    seed: int
    candidate_is_a: bool
    play_time: int
    limit_resources: bool
    catastrophic_penalty: float
    baseline_weights_json: str | None = None
    quiet: bool = True


@dataclass
class GameResult:
    seed: int
    opponent_name: str
    candidate_is_a: bool
    margin: float
    win_reason: str
    winner: str
    candidate_score: int
    opponent_score: int
    timed_out: bool
    invalid_turn: bool
    crashed: bool
    memory_error: bool
    failed_init: bool
    catastrophic_loss: bool


@dataclass
class SeriesResult:
    opponent_name: str
    avg_margin: float
    games: int
    wins: int
    losses: int
    ties: int
    timeouts: int
    invalid_turns: int
    crashes: int
    memory_errors: int
    failed_inits: int
    catastrophic_losses: int
    margins: list[float]


@dataclass
class FitnessResult:
    fitness: float
    profile: str
    ladder: list[dict[str, object]]
    weights: dict[str, float]
    strict_validation_passed: bool | None = None
    regression_passed: bool | None = None


DEFAULT_LADDER: tuple[OpponentConfig, ...] = (
    OpponentConfig("RandomSearchBaseline", 0.10, 40),
    OpponentConfig("yolanda_mitchell5", 0.225, 40),
    OpponentConfig("yolanda_mitch1_2", 0.225, 40),
    OpponentConfig("Yolanda6", 0.225, 40),
    OpponentConfig("yolanda_prime_v1_2_baseline", 0.225, 40),
)

HYPEROPT_LADDER: tuple[OpponentConfig, ...] = (
    # Tuned to match the project's “definitive improvement” bar:
    # - include yolanda_prime_v1_2_baseline, Yolanda3_3, Yolanda5
    # - keep RandomSearchBaseline with much smaller weight
    OpponentConfig("yolanda_prime_v1_2_baseline", 0.35, 50),
    OpponentConfig("Yolanda3_3", 0.20, 50),
    OpponentConfig("Yolanda5", 0.20, 50),
    OpponentConfig("Yolanda6", 0.15, 50),
    OpponentConfig("yolanda_mitch1_2", 0.075, 50),
    OpponentConfig("RandomSearchBaseline", 0.025, 30),
)

SMOKE_LADDER: tuple[OpponentConfig, ...] = (
    OpponentConfig("RandomSearchBaseline", 0.10, 2),
    OpponentConfig("yolanda_mitchell5", 0.225, 2),
    OpponentConfig("yolanda_mitch1_2", 0.225, 2),
    OpponentConfig("Yolanda6", 0.225, 2),
    OpponentConfig("yolanda_prime_v1_2_baseline", 0.225, 2),
)

STRICT_VALIDATION_OPPONENTS: tuple[str, ...] = (
    "yolanda_mitch1_2",
    "Yolanda6",
    "yolanda_prime_v1_2_baseline",
)

PROFILE_SETTINGS: dict[str, tuple[int, bool]] = {
    "smoke": (30, False),
    "tuning_fast": (60, False),
    "tuning": (240, False),
    "strict": (240, True),
    "local": (360, False),
}

_CATASTROPHIC_REASONS = {
    WinReason.TIMEOUT,
    WinReason.INVALID_TURN,
    WinReason.CODE_CRASH,
    WinReason.MEMORY_ERROR,
    WinReason.FAILED_INIT,
}


def available_profiles() -> tuple[str, ...]:
    return tuple(PROFILE_SETTINGS.keys())


def ladder_from_name(name: str) -> tuple[OpponentConfig, ...]:
    if name == "default":
        return DEFAULT_LADDER
    if name == "hyperopt":
        return HYPEROPT_LADDER
    if name == "smoke":
        return SMOKE_LADDER
    raise KeyError(f"unknown ladder preset: {name}")


def _score_rate(series: SeriesResult) -> float:
    return (series.wins + 0.5 * series.ties) / max(1, series.games)


def profile_settings(profile: str) -> tuple[int, bool]:
    if profile not in PROFILE_SETTINGS:
        raise KeyError(f"unknown evaluation profile: {profile}")
    return PROFILE_SETTINGS[profile]


@contextlib.contextmanager
def temporary_env(updates: Mapping[str, str | None]):
    previous = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _absolute_ab_scores(board) -> tuple[int, int]:
    if board.player_worker.is_player_a:
        return board.player_worker.get_points(), board.opponent_worker.get_points()
    return board.opponent_worker.get_points(), board.player_worker.get_points()


def _candidate_winner(candidate_is_a: bool) -> ResultArbiter:
    return ResultArbiter.PLAYER_A if candidate_is_a else ResultArbiter.PLAYER_B


def _opponent_winner(candidate_is_a: bool) -> ResultArbiter:
    return ResultArbiter.PLAYER_B if candidate_is_a else ResultArbiter.PLAYER_A


def _normalize_winner(raw: object) -> ResultArbiter:
    if isinstance(raw, ResultArbiter):
        return raw
    try:
        return ResultArbiter(raw)
    except (TypeError, ValueError):
        return ResultArbiter.ERROR


def _normalize_reason(raw: object) -> WinReason:
    if isinstance(raw, WinReason):
        return raw
    try:
        return WinReason(raw)
    except (TypeError, ValueError):
        return WinReason.CODE_CRASH


def run_single_game(task: GameTask) -> GameResult:
    if task.opponent_name == "yolanda_prime_v1_2":
        raise ValueError(
            "Use yolanda_prime_v1_2_baseline for regression/self-play checks; "
            "yolanda_prime_v1_2 vs itself evaluates the candidate against itself."
        )

    # Candidate and baseline use separate env channels so self-play regression
    # checks do not accidentally compare the same weight vector twice.
    env_updates = {
        "YP12_WEIGHTS_JSON": task.candidate_weights_json,
        "YP12_BASELINE_WEIGHTS_JSON": task.baseline_weights_json,
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
            player_a = "yolanda_prime_v1_2" if task.candidate_is_a else task.opponent_name
            player_b = task.opponent_name if task.candidate_is_a else "yolanda_prime_v1_2"
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
                        f"FAILED_INIT in {player_a} vs {player_b} (seed={task.seed}) after {max_attempts} attempts "
                        f"A={msg_a!r} B={msg_b!r}"
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

    catastrophic_loss = winner == _opponent_winner(task.candidate_is_a) and win_reason in _CATASTROPHIC_REASONS
    margin = float(task.catastrophic_penalty if catastrophic_loss else candidate_score - opponent_score)

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


def _series_result(opponent_name: str, results: Sequence[GameResult]) -> SeriesResult:
    wins = sum(1 for result in results if result.winner == _candidate_winner(result.candidate_is_a).name)
    losses = sum(1 for result in results if result.winner == _opponent_winner(result.candidate_is_a).name)
    ties = sum(1 for result in results if result.winner == ResultArbiter.TIE.name)
    margins = [result.margin for result in results]
    avg_margin = sum(margins) / len(margins) if margins else float("-inf")
    return SeriesResult(
        opponent_name=opponent_name,
        avg_margin=avg_margin,
        games=len(results),
        wins=wins,
        losses=losses,
        ties=ties,
        timeouts=sum(result.timed_out for result in results),
        invalid_turns=sum(result.invalid_turn for result in results),
        crashes=sum(result.crashed for result in results),
        memory_errors=sum(result.memory_error for result in results),
        failed_inits=sum(result.failed_init for result in results),
        catastrophic_losses=sum(result.catastrophic_loss for result in results),
        margins=margins,
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
    ladder: Iterable[OpponentConfig] = DEFAULT_LADDER,
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
    series = evaluate_series(
        new_weights,
        "yolanda_prime_v1_2_baseline",
        games=games,
        seed_start=seed_start,
        profile=profile,
        baseline_weights=baseline_weights,
        quiet=quiet,
    )
    score_rate = (series.wins + 0.5 * series.ties) / max(1, series.games)
    details = asdict(series)
    details["score_rate"] = score_rate
    details["required_score_rate"] = required_score_rate
    return score_rate >= required_score_rate and series.catastrophic_losses == 0, details


def definitive_improvement_check(
    new_weights: Mapping[str, float],
    *,
    baseline_weights: Mapping[str, float] | None = None,
    opponents: Sequence[str] = ("yolanda_prime_v1_2_baseline", "Yolanda3_3", "Yolanda5", "RandomSearchBaseline"),
    games_per_opponent: int = 200,
    required_score_rate: float = 0.52,
    require_positive_margin: bool = True,
    seed_start: int = 500_000,
    profile: str = "tuning",
    quiet: bool = True,
) -> tuple[bool, dict[str, object]]:
    """
    “Definitive improvement” = beats each target opponent by BOTH:
    - win-rate proxy (score rate) above a threshold
    - positive average point margin (optional but recommended)
    """

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
            # Treat harness/opponent init failures as a failed definitive check,
            # but do not crash the whole optimization run at shutdown.
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
    "DEFAULTS",
    "DEFAULT_LADDER",
    "HYPEROPT_LADDER",
    "FitnessResult",
    "GameResult",
    "InfrastructureFailure",
    "OpponentConfig",
    "PARAMETER_PROFILES",
    "PROFILE_SETTINGS",
    "SMOKE_LADDER",
    "SeriesResult",
    "available_profiles",
    "bounds_for",
    "clamp_weights",
    "definitive_improvement_check",
    "evaluate_fitness",
    "evaluate_series",
    "ladder_from_name",
    "parameter_names",
    "profile_settings",
    "regression_check",
    "serialize_weights",
    "strict_mode_validation",
    "vector_to_weights",
    "weights_to_vector",
    "write_best_weights",
]

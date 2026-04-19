#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import os
import pickle
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflows.yp12_hyperopt import (
    DEFAULTS,
    PARAMETER_PROFILES,
    InfrastructureFailure,
    available_profiles,
    bounds_for,
    clamp_weights,
    definitive_improvement_check,
    evaluate_fitness,
    evaluate_series,
    ladder_from_name,
    regression_check,
    strict_mode_validation,
    vector_to_weights,
    weights_to_vector,
    write_best_weights,
)

DEFAULT_OUTPUT_DIR = ROOT / "data" / "hyperopt" / "yolanda_prime_v1_2"


def _ga_state_path(output_dir: Path) -> Path:
    return output_dir / "ga_state.pkl"


def _cma_state_path(output_dir: Path) -> Path:
    return output_dir / "cma_state.pkl"


def _load_json(path: str | Path | None) -> dict[str, float]:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _save_pickle(path: Path, payload: object) -> None:
    path.write_bytes(pickle.dumps(payload))


def _load_pickle(path: Path) -> object:
    return pickle.loads(path.read_bytes())


def _build_preflight_board(time_to_play: float = 240.0):
    from game.board import Board

    board = Board(time_to_play=time_to_play)
    board.player_worker.position = (3, 3)
    board.opponent_worker.position = (4, 4)
    return board


@contextlib.contextmanager
def _temporary_env(updates: dict[str, str | None]):
    previous = {name: os.environ.get(name) for name in updates}
    try:
        for name, value in updates.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _verify_weight_channel_isolation() -> None:
    from yolanda_prime_v1_2.agent import PlayerAgent as LiveAgent
    from yolanda_prime_v1_2.infra.time_manager import TimeManager
    from yolanda_prime_v1_2_baseline.agent import PlayerAgent as BaselineAgent

    env = {
        "YP12_WEIGHTS_JSON": json.dumps({"a": 2.1, "time_opening_cap": 4.0}),
        "YP12_BASELINE_WEIGHTS_JSON": json.dumps({"a": 0.9, "time_opening_cap": 2.0}),
    }
    with _temporary_env(env):
        live_agent = LiveAgent(_build_preflight_board(), time_left=lambda: 10.0)
        baseline_agent = BaselineAgent(_build_preflight_board(), time_left=lambda: 10.0)

    if abs(live_agent.policy_engine.a - 2.1) > 1e-9:
        raise RuntimeError("yolanda_prime_v1_2 did not load candidate weights from YP12_WEIGHTS_JSON")
    if abs(baseline_agent.policy_engine.a - 0.9) > 1e-9:
        raise RuntimeError(
            "yolanda_prime_v1_2_baseline did not load baseline weights from YP12_BASELINE_WEIGHTS_JSON"
        )
    if abs(TimeManager.phase_cap(0, baseline_agent.runtime_state) - 2.0) > 1e-9:
        raise RuntimeError("yolanda_prime_v1_2_baseline did not isolate baseline time-control weights")


def _preflight_stack(
    *,
    eval_profile: str,
    baseline_weights: dict[str, float] | None,
) -> None:
    """Fail fast on broken weight channeling or an invalid local evaluation harness."""

    _verify_weight_channel_isolation()
    for opponent_name in ("RandomSearchBaseline", "yolanda_prime_v1_2_baseline"):
        series = evaluate_series(
            DEFAULTS,
            opponent_name,
            games=1,
            seed_start=17,
            profile=eval_profile,
            workers=1,
            baseline_weights=baseline_weights,
            quiet=True,
        )
        if series.catastrophic_losses > 0:
            raise RuntimeError(f"Preflight series against {opponent_name} produced a candidate catastrophic loss")


def _evaluate_candidate(
    vector: np.ndarray,
    profile_name: str,
    ladder_name: str,
    eval_profile: str,
    seed_start: int,
    baseline_weights: dict[str, float] | None,
) -> tuple[float, dict[str, object]]:
    weights = vector_to_weights(vector.tolist(), profile=profile_name)
    result = evaluate_fitness(
        weights,
        ladder=ladder_from_name(ladder_name),
        profile=eval_profile,
        seed_start=seed_start,
        baseline_weights=baseline_weights,
    )
    return result.fitness, asdict(result)


def _ga_optimize(
    *,
    initial_vector: np.ndarray,
    profile_name: str,
    ladder_name: str,
    eval_profile: str,
    generations: int,
    population_size: int,
    mutation_sigma: float,
    max_workers: int,
    seed: int,
    baseline_weights: dict[str, float] | None,
    output_dir: Path,
    strict_check_interval: int,
    regression_games: int,
    regression_score_rate: float,
    resume: bool = False,
) -> dict[str, object]:
    rng = np.random.default_rng(seed)
    bounds = bounds_for(profile_name)
    dim = len(initial_vector)
    pop_size = max(2, population_size)
    elite_size = max(1, min(pop_size // 4, 8))
    state_path = _ga_state_path(output_dir)

    def clamp_vector(vec: np.ndarray) -> np.ndarray:
        out = vec.copy()
        for idx, (lower, upper) in enumerate(bounds):
            out[idx] = np.clip(out[idx], lower, upper)
        return out

    population: list[np.ndarray] = [initial_vector.copy()]
    while len(population) < pop_size:
        candidate = initial_vector + rng.normal(0.0, mutation_sigma, size=dim)
        population.append(clamp_vector(candidate))

    history: list[dict[str, object]] = []
    best_vector = initial_vector.copy()
    best_fitness = float("-inf")

    start_gen = 0
    if resume and state_path.exists():
        state = _load_pickle(state_path)
        if not isinstance(state, dict):
            raise RuntimeError(f"Corrupt GA resume state: {state_path}")
        if state.get("profile_name") != profile_name or state.get("ladder_name") != ladder_name:
            raise RuntimeError("GA resume state does not match the requested profile/ladder")
        start_gen = int(state["next_generation"])
        history = list(state["history"])
        best_vector = np.asarray(state["best_vector"], dtype=np.float64)
        best_fitness = float(state["best_fitness"])
        mutation_sigma = float(state["mutation_sigma"])
        population = [np.asarray(candidate, dtype=np.float64) for candidate in state["population"]]
        rng.bit_generator.state = state["rng_state"]
        print(f"Resuming GA from Generation {start_gen}...", flush=True)
    elif resume:
        history_json = output_dir / "history"
        if history_json.exists():
            files = sorted(history_json.glob("generation_*.json"))
            if files:
                latest = files[-1]
                try:
                    data = json.loads(latest.read_text())
                    start_gen = data["generation"] + 1
                    print(f"Resuming GA from legacy history at Generation {start_gen}...", flush=True)
                    if (output_dir / "best_weights.json").exists():
                        best_weights = _load_json(output_dir / "best_weights.json")
                        initial_vector = np.asarray(weights_to_vector(best_weights, profile=profile_name), dtype=np.float64)
                        population = [initial_vector.copy() + rng.normal(0, mutation_sigma, size=dim) for _ in range(pop_size)]
                        population[0] = initial_vector
                        best_vector = initial_vector.copy()
                except Exception:
                    pass

    for generation in range(start_gen, generations):
        import time

        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] Starting Generation {generation}/{generations}...", flush=True)

        seed_base = seed + generation * 50_000
        if max_workers <= 1:
            scored = [
                (candidate, *_evaluate_candidate(candidate, profile_name, ladder_name, eval_profile, seed_base, baseline_weights))
                for candidate in population
            ]
        else:
            with ProcessPoolExecutor(max_workers=max_workers) as pool:
                futures = [
                    pool.submit(
                        _evaluate_candidate,
                        candidate,
                        profile_name,
                        ladder_name,
                        eval_profile,
                        seed_base,
                        baseline_weights,
                    )
                    for candidate in population
                ]
                scored = []
                for idx, (candidate, future) in enumerate(zip(population, futures)):
                    try:
                        fitness, details = future.result()
                        scored.append((candidate, fitness, details))
                        print(f"  Candidate {idx + 1}/{len(population)} evaluated (fitness: {fitness:.3f})", flush=True)
                    except InfrastructureFailure:
                        raise
                    except Exception as exc:
                        print(f"  [ERROR] Candidate {idx} evaluation failed: {exc}", flush=True)
                        scored.append((candidate, -100.0, {"weights": {}}))

        scored.sort(key=lambda item: item[1], reverse=True)
        elites = [candidate.copy() for candidate, _, _ in scored[:elite_size]]
        generation_best_vector = elites[0]
        generation_best_fitness = scored[0][1]
        generation_best_details = scored[0][2]

        strict_passed = None
        strict_details = None
        if strict_check_interval > 0 and ((generation + 1) % strict_check_interval == 0):
            print("  Performing strict mode validation...", flush=True)
            strict_passed, strict_details = strict_mode_validation(
                vector_to_weights(generation_best_vector.tolist(), profile=profile_name)
            )
            status = "PASSED" if strict_passed else "FAILED"
            print(f"  [STRICT] {status}", flush=True)

        if generation_best_fitness > best_fitness:
            best_fitness = generation_best_fitness
            best_vector = generation_best_vector.copy()
            write_best_weights(output_dir / "best_weights.json", vector_to_weights(best_vector.tolist(), profile=profile_name))

        mean_fit = float(np.mean([item[1] for item in scored]))
        print(
            f"  Gen {generation} Summary: Best={generation_best_fitness:.3f} "
            f"Mean={mean_fit:.3f} Worst={scored[-1][1]:.3f}",
            flush=True,
        )

        history_entry = {
            "generation": generation,
            "best_fitness": generation_best_fitness,
            "mean_fitness": mean_fit,
            "worst_fitness": scored[-1][1],
            "weights": generation_best_details["weights"],
            "strict_validation_passed": strict_passed,
            "strict_validation_details": strict_details,
        }
        history.append(history_entry)
        (output_dir / "history").mkdir(parents=True, exist_ok=True)
        (output_dir / "history" / f"generation_{generation:03d}.json").write_text(
            json.dumps(history_entry, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        next_population = list(elites)
        while len(next_population) < pop_size:
            parent_a = elites[rng.integers(0, len(elites))]
            parent_b = elites[rng.integers(0, len(elites))]
            mask = rng.random(dim) >= 0.5
            child = np.where(mask, parent_a, parent_b)
            child = child + rng.normal(0.0, mutation_sigma, size=dim)
            next_population.append(clamp_vector(child))

        mutation_sigma *= 0.98
        population = next_population
        _save_pickle(
            state_path,
            {
                "profile_name": profile_name,
                "ladder_name": ladder_name,
                "next_generation": generation + 1,
                "mutation_sigma": mutation_sigma,
                "population": [candidate.tolist() for candidate in population],
                "best_vector": best_vector.tolist(),
                "best_fitness": best_fitness,
                "history": history,
                "rng_state": rng.bit_generator.state,
            },
        )

    best_weights = vector_to_weights(best_vector.tolist(), profile=profile_name)
    regression_passed, regression_details = regression_check(
        best_weights,
        baseline_weights=baseline_weights,
        games=regression_games,
        required_score_rate=regression_score_rate,
        profile=eval_profile,
    )
    best_evaluation = asdict(
        evaluate_fitness(
            best_weights,
            ladder=ladder_from_name(ladder_name),
            profile=eval_profile,
            seed_start=seed + 900_000,
            baseline_weights=baseline_weights,
        )
    )

    summary = {
        "algorithm": "ga",
        "parameter_profile": profile_name,
        "ladder": ladder_name,
        "evaluation_profile": eval_profile,
        "generations": generations,
        "population_size": pop_size,
        "max_workers": max_workers,
        "best_fitness": best_fitness,
        "best_weights": best_weights,
        "best_evaluation": best_evaluation,
        "regression_passed": regression_passed,
        "regression_details": regression_details,
        "history": history,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _cma_optimize(
    *,
    initial_vector: np.ndarray,
    profile_name: str,
    ladder_name: str,
    eval_profile: str,
    generations: int,
    population_size: int,
    sigma: float,
    max_workers: int,
    seed: int,
    baseline_weights: dict[str, float] | None,
    output_dir: Path,
    strict_check_interval: int,
    regression_games: int,
    regression_score_rate: float,
    resume: bool = False,
) -> dict[str, object]:
    start_gen = 0
    history = []
    best_vector = initial_vector
    best_fitness = float("-inf")
    state_path = _cma_state_path(output_dir)
    bounds = list(zip(*bounds_for(profile_name)))

    try:
        import cma
    except ImportError as exc:
        raise RuntimeError("pycma is not installed; rerun with --algo ga or install cma") from exc

    if resume and state_path.exists():
        state = _load_pickle(state_path)
        if not isinstance(state, dict):
            raise RuntimeError(f"Corrupt CMA resume state: {state_path}")
        if state.get("profile_name") != profile_name or state.get("ladder_name") != ladder_name:
            raise RuntimeError("CMA resume state does not match the requested profile/ladder")
        start_gen = int(state["generation"])
        history = list(state["history"])
        best_vector = np.asarray(state["best_vector"], dtype=np.float64)
        best_fitness = float(state["best_fitness"])
        best_weights = clamp_weights(state["best_weights"])
        es = state["es"]
        print(f"Resuming CMA from Generation {start_gen}...", flush=True)
        # If the checkpoint was created with a lower maxiter (e.g., 30) and the
        # user now requests a higher total generation target (e.g., 75), the
        # unpickled strategy can report a terminal maxiter stop immediately.
        # Re-seed a fresh CMA strategy around the incumbent best vector so resume
        # can continue optimizing toward the new requested target.
        if start_gen < generations and es.stop():
            stop_reasons = es.stop()
            only_maxiter_stop = set(stop_reasons.keys()) <= {"maxiter"}
            if only_maxiter_stop:
                sigma_for_resume = float(getattr(es, "sigma", sigma))
                es = cma.CMAEvolutionStrategy(
                    best_vector.tolist(),
                    sigma_for_resume,
                    {
                        "bounds": bounds,
                        "maxiter": generations,
                        "popsize": population_size,
                        "seed": seed + start_gen,
                        "verbose": -9,
                    },
                )
                print(
                    "Detected maxiter-limited checkpoint; reinitializing CMA state "
                    f"at Generation {start_gen} for target {generations}.",
                    flush=True,
                )
    else:
        best_weights = clamp_weights(DEFAULTS)
        if resume:
            history_dir = output_dir / "history"
            if history_dir.exists():
                files = sorted(history_dir.glob("generation_*.json"))
                if files:
                    latest = files[-1]
                    try:
                        data = json.loads(latest.read_text())
                        start_gen = data["generation"] + 1
                        best_weights = clamp_weights(data["weights"])
                        best_vector = np.asarray(weights_to_vector(best_weights, profile=profile_name), dtype=np.float64)
                        print(f"Resuming CMA from legacy history at Generation {start_gen}...", flush=True)
                    except Exception:
                        pass
        es = cma.CMAEvolutionStrategy(
            best_vector.tolist(),
            sigma,
            {
                "bounds": bounds,
                "maxiter": generations,
                "popsize": population_size,
                "seed": seed,
                "verbose": -9,
            },
        )

    generation = start_gen
    while not es.stop() and generation < generations:
        import time

        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] Starting Generation {generation}...", flush=True)

        candidates = [np.asarray(candidate, dtype=np.float64) for candidate in es.ask()]
        seed_base = seed + generation * 50_000
        if max_workers <= 1:
            evaluated = [
                _evaluate_candidate(candidate, profile_name, ladder_name, eval_profile, seed_base, baseline_weights)
                for candidate in candidates
            ]
        else:
            with ProcessPoolExecutor(max_workers=max_workers) as pool:
                futures = [
                    pool.submit(
                        _evaluate_candidate,
                        candidate,
                        profile_name,
                        ladder_name,
                        eval_profile,
                        seed_base,
                        baseline_weights,
                    )
                    for candidate in candidates
                ]
                evaluated = []
                for idx, future in enumerate(futures):
                    try:
                        result = future.result()
                        evaluated.append(result)
                        print(f"  Candidate {idx + 1}/{len(candidates)} evaluated (fitness: {result[0]:.3f})", flush=True)
                    except InfrastructureFailure:
                        raise
                    except Exception as exc:
                        print(f"  [ERROR] Candidate {idx} evaluation failed: {exc}", flush=True)
                        evaluated.append((-100.0, {"weights": {}}))

        fitnesses = [fitness for fitness, _details in evaluated]
        es.tell([candidate.tolist() for candidate in candidates], [-fitness for fitness in fitnesses])

        best_idx = int(np.argmax(fitnesses))
        generation_best_weights = vector_to_weights(candidates[best_idx].tolist(), profile=profile_name)
        generation_best_fitness = fitnesses[best_idx]

        mean_fit = float(np.mean(fitnesses))
        print(
            f"  Gen {generation} Summary: Best={generation_best_fitness:.3f} "
            f"Mean={mean_fit:.3f} Worst={float(np.min(fitnesses)):.3f}",
            flush=True,
        )

        strict_passed = None
        strict_details = None
        if strict_check_interval > 0 and ((generation + 1) % strict_check_interval == 0):
            print("  Performing strict mode validation...", flush=True)
            strict_passed, strict_details = strict_mode_validation(generation_best_weights)
            status = "PASSED" if strict_passed else "FAILED"
            print(f"  [STRICT] {status}", flush=True)

        if generation_best_fitness > best_fitness:
            best_fitness = generation_best_fitness
            best_vector = candidates[best_idx].copy()
            best_weights = generation_best_weights
            write_best_weights(output_dir / "best_weights.json", best_weights)

        history_entry = {
            "generation": generation,
            "best_fitness": generation_best_fitness,
            "mean_fitness": mean_fit,
            "worst_fitness": float(np.min(fitnesses)),
            "weights": generation_best_weights,
            "strict_validation_passed": strict_passed,
            "strict_validation_details": strict_details,
        }
        history.append(history_entry)
        (output_dir / "history").mkdir(parents=True, exist_ok=True)
        (output_dir / "history" / f"generation_{generation:03d}.json").write_text(
            json.dumps(history_entry, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        generation += 1
        _save_pickle(
            state_path,
            {
                "profile_name": profile_name,
                "ladder_name": ladder_name,
                "generation": generation,
                "best_vector": best_vector.tolist(),
                "best_weights": best_weights,
                "best_fitness": best_fitness,
                "history": history,
                "es": es,
            },
        )

    regression_passed, regression_details = regression_check(
        best_weights,
        baseline_weights=baseline_weights,
        games=regression_games,
        required_score_rate=regression_score_rate,
        profile=eval_profile,
    )
    best_evaluation = asdict(
        evaluate_fitness(
            best_weights,
            ladder=ladder_from_name(ladder_name),
            profile=eval_profile,
            seed_start=seed + 900_000,
            baseline_weights=baseline_weights,
        )
    )

    summary = {
        "algorithm": "cma",
        "parameter_profile": profile_name,
        "ladder": ladder_name,
        "evaluation_profile": eval_profile,
        "generations": generation,
        "population_size": population_size,
        "max_workers": max_workers,
        "best_fitness": best_fitness,
        "best_weights": best_weights,
        "best_evaluation": best_evaluation,
        "regression_passed": regression_passed,
        "regression_details": regression_details,
        "history": history,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline black-box optimizer for yolanda_prime_v1_2 weights.")
    parser.add_argument("--algo", choices=("auto", "cma", "ga"), default="auto")
    parser.add_argument(
        "--profile",
        choices=tuple(PARAMETER_PROFILES.keys()),
        default="core",
        help="Weight subspace to optimize",
    )
    parser.add_argument(
        "--ladder",
        choices=("default", "hyperopt", "smoke"),
        default="smoke",
        help="Opponent ladder preset",
    )
    parser.add_argument("--evaluation-profile", choices=available_profiles(), default="tuning")
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--population", type=int, default=6)
    parser.add_argument("--sigma", type=float, default=0.20, help="Initial mutation scale / CMA sigma")
    parser.add_argument("--workers", type=int, default=max(1, os.cpu_count() or 1))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--strict-check-interval", type=int, default=5)
    parser.add_argument("--regression-games", type=int, default=20)
    parser.add_argument("--regression-score-rate", type=float, default=0.55)
    parser.add_argument("--definitive-games", type=int, default=200)
    parser.add_argument("--definitive-score-rate", type=float, default=0.52)
    parser.add_argument(
        "--definitive-require-positive-margin",
        dest="definitive_require_positive_margin",
        action="store_true",
        default=True,
        help="Require avg_margin > 0.0 versus each definitive-check opponent (default: enabled)",
    )
    parser.add_argument(
        "--definitive-allow-nonpositive-margin",
        dest="definitive_require_positive_margin",
        action="store_false",
        help="Disable positive-margin requirement for definitive checks (not recommended)",
    )
    parser.add_argument("--initial-weights-file", help="Optional JSON file with starting weights")
    parser.add_argument(
        "--baseline-weights-file",
        help="Optional JSON file used by yolanda_prime_v1_2_baseline during regression/self-play",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--resume", action="store_true", help="Resume from output_dir if history exists")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip fast stack validation before the long run")
    args = parser.parse_args()

    profile_name = args.profile
    initial_weights = clamp_weights(DEFAULTS | _load_json(args.initial_weights_file))
    initial_vector = np.asarray(weights_to_vector(initial_weights, profile=profile_name), dtype=np.float64)
    baseline_weights = _load_json(args.baseline_weights_file) if args.baseline_weights_file else None
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    algorithm = args.algo
    if algorithm == "auto":
        algorithm = "cma"
        try:
            import cma  # noqa: F401
        except ImportError:
            algorithm = "ga"
    print(f"Selected optimizer: {algorithm}", flush=True)

    if not args.skip_preflight:
        print("Running hyperopt preflight...", flush=True)
        _preflight_stack(
            eval_profile=args.evaluation_profile,
            baseline_weights=baseline_weights,
        )
        print("Preflight passed.", flush=True)

    if algorithm == "cma":
        summary = _cma_optimize(
            initial_vector=initial_vector,
            profile_name=profile_name,
            ladder_name=args.ladder,
            eval_profile=args.evaluation_profile,
            generations=args.generations,
            population_size=args.population,
            sigma=args.sigma,
            max_workers=max(1, args.workers),
            seed=args.seed,
            baseline_weights=baseline_weights,
            output_dir=output_dir,
            strict_check_interval=args.strict_check_interval,
            regression_games=args.regression_games,
            regression_score_rate=args.regression_score_rate,
            resume=args.resume,
        )
    else:
        summary = _ga_optimize(
            initial_vector=initial_vector,
            profile_name=profile_name,
            ladder_name=args.ladder,
            eval_profile=args.evaluation_profile,
            generations=args.generations,
            population_size=args.population,
            mutation_sigma=args.sigma,
            max_workers=max(1, args.workers),
            seed=args.seed,
            baseline_weights=baseline_weights,
            output_dir=output_dir,
            strict_check_interval=args.strict_check_interval,
            regression_games=args.regression_games,
            regression_score_rate=args.regression_score_rate,
            resume=args.resume,
        )

    best_weights = summary.get("best_weights")
    if isinstance(best_weights, dict):
        definitive_passed, definitive_details = definitive_improvement_check(
            best_weights,
            baseline_weights=baseline_weights,
            games_per_opponent=int(args.definitive_games),
            required_score_rate=float(args.definitive_score_rate),
            require_positive_margin=bool(args.definitive_require_positive_margin),
            profile=args.evaluation_profile,
            quiet=True,
        )
        summary["definitive_improvement_passed"] = definitive_passed
        summary["definitive_improvement_details"] = definitive_details

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

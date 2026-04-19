# CS3600: The Carpet Game Tournament (Spring 2026)

AI agent readable assignment instructions are extracted from `docs/assignment.pdf` and are available in `docs/assignment_spec.md`.

Plan for the bot is placed in `docs/bot_plan_v4.md`.

## Project Structure

- `3600-agents/Yolanda/`: Primary agent implementation.
  - `agent.py`: Main entry point orchestrating belief tracking and strategy.
  - `tracking/`: HMM-based belief engine for rat localization and opponent observation.
  - `strategy/`: Policy engine with adaptive heuristic scoring and endgame rollouts.
  - `infra/`: Runtime state management and tournament-aware timing logic.
- `engine/`: Tournament game engine and mechanics.
- `tests/`: Unit tests and contract verification.
- `workflows/`: Specialized evaluation and reporting scripts (including `master_batch.py` for arbitrary matchups).
- `scripts/`: Validation and automation entry points.
- `docs/`: Technical specifications, strategy deep-dives, and milestone reports.
- `logs/`: Runtime logs and validation artifacts.
- `data/`: Match results and historical data.

## Yolanda Agent Deep Dive

### 1. Belief & Tracking
- **HMM Engine**: Maintains a Hidden Markov Model over the grid. It uses precomputed transition matrices to predict rat movement and integrates sensor data (noise/distance) via Bayesian updates.
- **Split-Step Propagation**: Correctly accounts for turn parity and "opponent misses" to refine the probability distribution even when Yolanda isn't the one searching.
- **Rat Concentration Analysis**: Detects "farmable" transition matrices where rats tend to cluster, allowing for more efficient search-to-score ratios.

### 2. Strategic Policy
- **Heuristic Evaluation**: Moves are evaluated using a multi-objective scoring function:
  - **Immediate Gain**: Points from priming or carpeting.
  - **Mobility & Centrality**: Prioritizes staying in open, central areas to maintain options.
  - **Board Control**: Actively penalizes actions that fragment the board or trap the agent.
  - **Opponent Denial**: Prefers moves that restrict the opponent's available tiles.
- **Phase Adaptation**: Heuristic weights shift dynamically between **Opening**, **Mid**, and **Late** game phases.
- **Score Pressure**: Yolanda detects if she is trailing and increases risk tolerance to catch up, or plays defensively when holding a safe lead.

### 3. Competitor Modeling
- **Opponent Classification**: Observes opponent moves to categorize their playstyle (Aggressive, Defensive, Search-heavy).
- **Dynamic Coefficient Tuning**: Adjusts internal strategy parameters in real-time to counter the detected opponent pattern.

### 4. Endgame Logic
- **Greedy Rollouts**: In the final 3 turns, Yolanda switches from heuristic scoring to exact depth-k greedy rollouts.
- **Win Probability Maximization**: Calculates the probability of winning if a search is successful versus if it fails, ensuring optimal "hail-mary" behavior if trailing at the buzzer.

## Head-to-head batch (`workflows/master_batch.py`)

Run many games between any two agent packages under `3600-agents/` (each package is a directory with `agent.py`).

**Environment:** The engine needs Python packages (at least `numpy` and `psutil`). Use the project venv when possible:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**List available bots:**

```bash
.venv/bin/python workflows/master_batch.py --list-bots
```

**Run a series** — first bot name is the reference for printed win counts and score delta (first minus second). By default, who plays as player A alternates each game.

```bash
.venv/bin/python workflows/master_batch.py Yolanda RandomSearchBaseline --games 12 --quiet
.venv/bin/python workflows/master_batch.py Yolanda Yolanda1 --profile local --games 20 --quiet
```

**Common flags:**

| Flag | Meaning |
|------|--------|
| `--profile strict` | 240s per player; on Linux, engine resource limits match the tournament default |
| `--profile local` | 360s per player, no resource limits (comfortable local smoke) |
| `--games N` | Number of games |
| `--seed-start` | Base seed; game `g` uses `seed_start + g` |
| `--no-alternate-sides` | Keep the first bot as player A every game |
| `--quiet` | Suppress per-move output from child processes |

Full options: `.venv/bin/python workflows/master_batch.py --help`.

## Yolanda4 hyperparameter tuning

The Yolanda4 tuning stack lives in:

- `3600-agents/Yolanda4/infra/weights.py`: centralized tunable parameter definitions, bounds, and loader
- `3600-agents/Yolanda4Baseline/`: frozen-weight wrapper used for candidate-vs-baseline self-play
- `workflows/y4_hyperopt.py`: evaluation, fitness aggregation, strict validation, regression check helpers
- `scripts/evaluate_weights.py`: one-opponent evaluator
- `scripts/optimize_weights.py`: CMA-ES/GA optimizer with preflight validation, common-random-number evaluation, and resumable state
- `scripts/y4_hyperopt_pace.slurm`: PACE batch template

PACE/default ladder opponents:

- `RandomSearchBaseline`
- `yolanda_mitchell5`
- `yolanda_mitch1_2`
- `Yolanda3_3`
- `Yolanda4Baseline`

Local smoke evaluation:

```bash
.venv/bin/python scripts/evaluate_weights.py RandomSearchBaseline --games 4 --profile smoke
.venv/bin/python scripts/evaluate_weights.py Yolanda4Baseline --games 4 --profile smoke
```

Local smoke optimization:

```bash
.venv/bin/python scripts/optimize_weights.py \
  --algo ga \
  --profile tier_ab \
  --ladder smoke \
  --evaluation-profile smoke \
  --generations 3 \
  --population 6 \
  --workers 4 \
  --output-dir data/hyperopt/yolanda4/local_smoke
```

Overnight local run:

```bash
.venv/bin/python scripts/optimize_weights.py \
  --algo auto \
  --profile tier_ab \
  --ladder default \
  --evaluation-profile tuning \
  --generations 30 \
  --population 12 \
  --workers 8 \
  --strict-check-interval 5 \
  --regression-games 30 \
  --output-dir data/hyperopt/yolanda4/local_full
```

PACE:

```bash
sbatch scripts/y4_hyperopt_pace.slurm
```

When you trust a tuned run, copy the chosen `best_weights.json` into `3600-agents/Yolanda4/weights.json` so the package loads it by default. The optimizer now writes the full merged weight vector, so the artifact can be dropped in directly without reconstructing omitted defaults.

## Yolanda Prime v1.2 hyperparameter tuning

The yolanda_prime_v1_2 tuning stack lives in:

- `3600-agents/yolanda_prime_v1_2/infra/weights.py`: yp12 tunable parameter specs, bounds, and loaders
- `3600-agents/yolanda_prime_v1_2_baseline/`: frozen-weight baseline wrapper used for candidate-vs-baseline checks
- `workflows/yp12_hyperopt.py`: game harness, ladder definitions, fitness, strict validation, regression, and definitive-improvement checks
- `scripts/optimize_yp12_weights.py`: CMA-ES/GA optimizer with preflight validation and resumable state
- `scripts/yp12_hyperopt_pace.slurm`: PACE batch template for long runs

Baseline local smoke:

```bash
.venv/bin/python scripts/optimize_yp12_weights.py \
  --algo ga \
  --profile core \
  --ladder smoke \
  --evaluation-profile smoke \
  --generations 1 \
  --population 2 \
  --workers 1 \
  --regression-games 4 \
  --definitive-games 4 \
  --output-dir data/hyperopt/yolanda_prime_v1_2/local_smoke
```

Overnight local run:

```bash
.venv/bin/python scripts/optimize_yp12_weights.py \
  --algo auto \
  --profile core \
  --ladder hyperopt \
  --evaluation-profile tuning \
  --generations 30 \
  --population 12 \
  --workers 8 \
  --strict-check-interval 5 \
  --regression-games 30 \
  --definitive-games 200 \
  --output-dir data/hyperopt/yolanda_prime_v1_2/local_full \
  --resume
```

PACE:

```bash
sbatch scripts/yp12_hyperopt_pace.slurm
```

## M0 validation workflow

Canonical end-to-end command:

```bash
./scripts/validate_m0.sh --python python3.13 --restricted
```

This script runs venv setup, dependency install, `quality_guard`, unrestricted runtime smoke,
and restricted submission validation. It writes timestamped logs to `logs/m0_validation/`.

Important: M0 is only considered fully validated when restricted validation prints a
standalone `True` line (not `False`) and the script exits successfully.

macOS note:
- macOS may fail engine RLIMIT checks during restricted validation even when core logic is correct.
- Default macOS behavior is to log a warning and continue as "macOS-validated".
- To require strict restricted pass even on macOS, use:

```bash
./scripts/validate_m0.sh --python python3.13 --restricted --strict-restricted
```

Manual workflow (equivalent base checks):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python workflows/quality_guard.py
```

Primary M0 artifacts are available in `docs/` and `logs/`:

- `docs/m0_discrepancy_evidence_report.md` (always generated)
- `docs/next_steps_suggestion.txt` (generated on PASS)
- `logs/major_flaw_report.txt` (generated on failure)

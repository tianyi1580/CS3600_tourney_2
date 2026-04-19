#!/bin/bash
#SBATCH -J yp2-hyperopt
#SBATCH --account=paceship-terratrends
#SBATCH -q inferno
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=12G
#SBATCH -t 48:00:00
#SBATCH -o logs/yp2_hyperopt_%j.out
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=tma94@gatech.edu

# CMA-ES hyperoptimization for yolanda_prime_v2.
# Resource budget mirrors yp12 (16 CPUs, 12 GB, 48h wall) so comparable
# convergence is expected against the 330-games/candidate v2 ladder.
# Two-stage option: Stage 1 tunes the ``core`` profile (21 dims) with
# popsize 24; Stage 2 (opt-in via ``RUN_PHASE2=1``) warm-starts from
# Stage-1 best and extends the search to the ``phase`` profile (36 dims,
# adds the 15 phase multipliers) at a tighter sigma.

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
cd "$PROJECT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
# Fast-search shortcut lives outside the ``core`` optimization profile now.
# Pin it off so behavior is deterministic even if a stray env export tries
# to flip it back on between stages.
export Y3_ENABLE_FAST_SEARCH=0

WORKERS="${WORKERS:-${SLURM_CPUS_PER_TASK:-16}}"
RUN_DIR="${RUN_DIR:-data/hyperopt/yolanda_prime_v2/pace_run}"
GENERATIONS="${GENERATIONS:-30}"
POPULATION="${POPULATION:-24}"
SIGMA="${SIGMA:-0.25}"
REGRESSION_GAMES="${REGRESSION_GAMES:-30}"
STRICT_CHECK_INTERVAL="${STRICT_CHECK_INTERVAL:-5}"
GENERATION_EVAL_MODE="${GENERATION_EVAL_MODE:-flattened}"
ENABLE_DYNAMIC_BUDGET="${ENABLE_DYNAMIC_BUDGET:-1}"
BUDGET_SCHEDULE="${BUDGET_SCHEDULE:-0-10:200,11-20:260,21-9999:330}"
ENABLE_MERCY_RULE="${ENABLE_MERCY_RULE:-1}"
MERCY_STAGE_A_FRACTION="${MERCY_STAGE_A_FRACTION:-0.5}"
MERCY_MIN_GAMES="${MERCY_MIN_GAMES:-120}"
MERCY_FIXED_MARGIN_FLOOR="${MERCY_FIXED_MARGIN_FLOOR:--5.0}"
MERCY_PENALTY="${MERCY_PENALTY:-1.0}"
# Stage-2 phase profile tuning is opt-in: set RUN_PHASE2=1 to warm-start a
# second CMA run from the Stage-1 best, tuning the 15 phase multipliers.
RUN_PHASE2="${RUN_PHASE2:-0}"
PHASE2_GENERATIONS="${PHASE2_GENERATIONS:-12}"
PHASE2_POPULATION="${PHASE2_POPULATION:-20}"
PHASE2_SIGMA="${PHASE2_SIGMA:-0.15}"
echo "RUN_DIR=$RUN_DIR GENERATIONS=$GENERATIONS POPULATION=$POPULATION SIGMA=$SIGMA WORKERS=$WORKERS RUN_PHASE2=$RUN_PHASE2"

mkdir -p logs "$RUN_DIR"

EXTRA_EVAL_FLAGS=()
if [[ "$ENABLE_DYNAMIC_BUDGET" == "1" ]]; then
  EXTRA_EVAL_FLAGS+=(--enable-dynamic-budget)
fi
if [[ "$ENABLE_MERCY_RULE" == "1" ]]; then
  EXTRA_EVAL_FLAGS+=(--enable-mercy-rule)
fi

if ! "$PYTHON_BIN" -c "import cma, numpy, psutil" >/dev/null 2>&1; then
  if [[ "${AUTO_INSTALL_DEPS:-0}" == "1" ]]; then
    "$PYTHON_BIN" -m pip install -r requirements.txt
  else
    echo "Missing Python deps (cma/numpy/psutil)."
    echo "Create/activate a venv and install requirements, or set AUTO_INSTALL_DEPS=1."
    exit 2
  fi
fi

"$PYTHON_BIN" scripts/optimize_yp2_weights.py \
  --algo cma \
  --profile core \
  --ladder hyperopt \
  --evaluation-profile tuning \
  --generations "$GENERATIONS" \
  --population "$POPULATION" \
  --sigma "$SIGMA" \
  --workers "$WORKERS" \
  --strict-check-interval "$STRICT_CHECK_INTERVAL" \
  --generation-eval-mode "$GENERATION_EVAL_MODE" \
  --budget-schedule "$BUDGET_SCHEDULE" \
  --mercy-stage-a-fraction "$MERCY_STAGE_A_FRACTION" \
  --mercy-min-games "$MERCY_MIN_GAMES" \
  --mercy-fixed-margin-floor "$MERCY_FIXED_MARGIN_FLOOR" \
  --mercy-penalty "$MERCY_PENALTY" \
  --regression-games "$REGRESSION_GAMES" \
  --definitive-require-positive-margin \
  "${EXTRA_EVAL_FLAGS[@]}" \
  --output-dir "$RUN_DIR" \
  --resume

if [[ "$RUN_PHASE2" == "1" ]]; then
  PHASE2_DIR="${RUN_DIR}_phase"
  echo "Starting Stage-2 phase-profile tuning at $PHASE2_DIR (warm start from $RUN_DIR/best_weights.json)"
  mkdir -p "$PHASE2_DIR"
  "$PYTHON_BIN" scripts/optimize_yp2_weights.py \
    --algo cma \
    --profile phase \
    --ladder hyperopt \
    --evaluation-profile tuning \
    --generations "$PHASE2_GENERATIONS" \
    --population "$PHASE2_POPULATION" \
    --sigma "$PHASE2_SIGMA" \
    --workers "$WORKERS" \
    --strict-check-interval "$STRICT_CHECK_INTERVAL" \
    --generation-eval-mode "$GENERATION_EVAL_MODE" \
    --budget-schedule "$BUDGET_SCHEDULE" \
    --mercy-stage-a-fraction "$MERCY_STAGE_A_FRACTION" \
    --mercy-min-games "$MERCY_MIN_GAMES" \
    --mercy-fixed-margin-floor "$MERCY_FIXED_MARGIN_FLOOR" \
    --mercy-penalty "$MERCY_PENALTY" \
    --regression-games "$REGRESSION_GAMES" \
    --definitive-require-positive-margin \
    "${EXTRA_EVAL_FLAGS[@]}" \
    --initial-weights-file "$RUN_DIR/best_weights.json" \
    --output-dir "$PHASE2_DIR" \
    --resume
fi

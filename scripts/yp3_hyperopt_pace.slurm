#!/bin/bash
#SBATCH -J yp3-hyperopt
#SBATCH --account=paceship-terratrends
#SBATCH -q inferno
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=24
#SBATCH --mem=32G
#SBATCH -t 48:00:00
#SBATCH -o logs/yp3_hyperopt_%j.out
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=tma94@gatech.edu

# CMA-ES hyperoptimization for yolanda_prime_v3.
# This script enables the Mercy Rule and Dynamic Budgeting to make the 100s/game
# runtime feasible on PACE.

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
cd "$PROJECT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

export PYTHONUNBUFFERED=1

# Configuration
WORKERS="${WORKERS:-${SLURM_CPUS_PER_TASK:-64}}"
SIGMA="${SIGMA:-0.25}"
POPULATION="${POPULATION:-24}"

# 1. Dynamic Budget & Mercy Settings (Aggressive scaling for 200s games)
ENABLE_DYNAMIC_BUDGET=1
ENABLE_MERCY_RULE=1
BUDGET_SCHEDULE="0-5:10,6-15:16,16-9999:24" # Reduced for 200s games
MERCY_MIN_GAMES=10
MERCY_STAGE_A_FRACTION=0.30
MERCY_FIXED_MARGIN_FLOOR=-12.0

mkdir -p logs data/hyperopt/yolanda_prime_v3

EXTRA_EVAL_FLAGS=()
if [[ "$ENABLE_DYNAMIC_BUDGET" == "1" ]]; then
  EXTRA_EVAL_FLAGS+=(--enable-dynamic-budget)
fi
if [[ "$ENABLE_MERCY_RULE" == "1" ]]; then
  EXTRA_EVAL_FLAGS+=(--enable-mercy-rule --mercy-stage-a-fraction "$MERCY_STAGE_A_FRACTION")
fi

# ==============================================================================
# PHASE 1: CORE EVALUATOR (Tier A)
# ==============================================================================
STAGE1_DIR="data/hyperopt/yolanda_prime_v3/stage1_core"
echo "Starting YP3 Stage 1: Core Evaluator Optimization..."
"$PYTHON_BIN" scripts/optimize_yp3_weights.py \
  --algo cma \
  --profile core \
  --ladder hyperopt \
  --evaluation-profile tuning \
  --generations 15 \
  --population 12 \
  --sigma "$SIGMA" \
  --workers "$WORKERS" \
  --budget-schedule "$BUDGET_SCHEDULE" \
  --mercy-min-games "$MERCY_MIN_GAMES" \
  --mercy-fixed-margin-floor "$MERCY_FIXED_MARGIN_FLOOR" \
  "${EXTRA_EVAL_FLAGS[@]}" \
  --output-dir "$STAGE1_DIR" \
  --resume

# ==============================================================================
# PHASE 2: EXTENDED (All Parameters)
# ==============================================================================
STAGE2_DIR="data/hyperopt/yolanda_prime_v3/stage2_extended"
echo "Starting YP3 Stage 2: Extended (Full weights.json) Optimization..."
"$PYTHON_BIN" scripts/optimize_yp3_weights.py \
  --algo cma \
  --profile extended \
  --ladder hyperopt \
  --evaluation-profile tuning \
  --generations 15 \
  --population 16 \
  --sigma 0.15 \
  --workers "$WORKERS" \
  --budget-schedule "0-9999:32" \
  --mercy-min-games "$MERCY_MIN_GAMES" \
  --mercy-fixed-margin-floor "$MERCY_FIXED_MARGIN_FLOOR" \
  "${EXTRA_EVAL_FLAGS[@]}" \
  --initial-weights-file "$STAGE1_DIR/best_weights.json" \
  --output-dir "$STAGE2_DIR" \
  --resume


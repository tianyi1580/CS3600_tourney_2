#!/bin/bash
#SBATCH -J yp4-hyperopt
#SBATCH --account=paceship-terratrends
#SBATCH -q inferno
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=24
#SBATCH --mem=64G
#SBATCH -t 20:00:00
#SBATCH -o yp4_hpo_%j.out
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=tma94@gatech.edu

set -euo pipefail

# Robust discovery (V3 logic)
PROJECT_DIR="${PROJECT_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
cd "$PROJECT_DIR"

# Python detection
PYTHON_BIN="python3"
if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi
export PYTHONUNBUFFERED=1

echo "YP4 HPO Start: $(date)"
echo "Project: $PROJECT_DIR"
echo "Python: $PYTHON_BIN"

# Phase 1: Core Evaluator Tuning (Fast Pruning)
echo "Starting Stage 1: Core (Tuning α, β, γ, δ, ε, ω)..."
"$PYTHON_BIN" scripts/optimize_yp4_weights.py \
    --algo cma --generations 8 --population 24 \
    --profile core --ladder hyperopt --workers 24 \
    --enable-mercy-rule --mercy-min-games 3 --mercy-floor-25 -6.0 \
    --enable-dynamic-budget --budget-schedule "0-4:15,5-8:24" \
    --initial-weights-file 3600-agents/yolanda_prime_v4_7/weights.json \
    --output-dir "data/hyperopt/yolanda_prime_v4_7/stage1_core" \
    --resume

# Phase 2: Extended Parameter Tuning (Balanced Pruning)
echo "Starting Stage 2: Full (Search Policy + Time Management)..."
"$PYTHON_BIN" scripts/optimize_yp4_weights.py \
    --algo cma --generations 8 --population 24 \
    --profile extended --ladder hyperopt --workers 24 \
    --enable-mercy-rule --mercy-min-games 5 --mercy-floor-25 -5.0 \
    --enable-dynamic-budget --budget-schedule "0-4:20,5-8:30" \
    --initial-weights-file "data/hyperopt/yolanda_prime_v4_7/stage1_core/best_weights.json" \
    --output-dir "data/hyperopt/yolanda_prime_v4_7/stage2_extended" \
    --resume

echo "HPO Complete: $(date)"

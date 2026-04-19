#!/bin/bash
#SBATCH -J y4-hyperopt
#SBATCH --account=paceship-terratrends
#SBATCH -q inferno
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=12G
#SBATCH -t 48:00:00                          # Increased for full 30-gen run
#SBATCH -o logs/y4_hyperopt_%j.out
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=tma94@gatech.edu         # Notifications will go here

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

WORKERS="${WORKERS:-${SLURM_CPUS_PER_TASK:-16}}"
RUN_DIR="${RUN_DIR:-data/hyperopt/yolanda4/pace_run}"

mkdir -p logs "$RUN_DIR"

"$PYTHON_BIN" -c "import cma, numpy, psutil" >/dev/null

"$PYTHON_BIN" scripts/optimize_weights.py \
  --algo cma \
  --profile tier_ab \
  --ladder default \
  --evaluation-profile tuning \
  --generations 30 \
  --population 12 \
  --sigma 0.20 \
  --workers "$WORKERS" \
  --strict-check-interval 5 \
  --regression-games 30 \
  --output-dir "$RUN_DIR" \
  --resume

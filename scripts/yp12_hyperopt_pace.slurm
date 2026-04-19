#!/bin/bash
#SBATCH -J yp12-hyperopt
#SBATCH --account=paceship-terratrends
#SBATCH -q inferno
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=12G
#SBATCH -t 48:00:00
#SBATCH -o logs/yp12_hyperopt_%j.out
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=tma94@gatech.edu

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
RUN_DIR="${RUN_DIR:-data/hyperopt/yolanda_prime_v1_2/pace_run}"
GENERATIONS="${GENERATIONS:-30}"
POPULATION="${POPULATION:-12}"
SIGMA="${SIGMA:-0.20}"
REGRESSION_GAMES="${REGRESSION_GAMES:-30}"
STRICT_CHECK_INTERVAL="${STRICT_CHECK_INTERVAL:-5}"
echo "RUN_DIR=$RUN_DIR GENERATIONS=$GENERATIONS POPULATION=$POPULATION SIGMA=$SIGMA WORKERS=$WORKERS"

mkdir -p logs "$RUN_DIR"

if ! "$PYTHON_BIN" -c "import cma, numpy, psutil" >/dev/null 2>&1; then
  if [[ "${AUTO_INSTALL_DEPS:-0}" == "1" ]]; then
    "$PYTHON_BIN" -m pip install -r requirements.txt
  else
    echo "Missing Python deps (cma/numpy/psutil)."
    echo "Create/activate a venv and install requirements, or set AUTO_INSTALL_DEPS=1."
    exit 2
  fi
fi

"$PYTHON_BIN" scripts/optimize_yp12_weights.py \
  --algo cma \
  --profile core \
  --ladder hyperopt \
  --evaluation-profile tuning \
  --generations "$GENERATIONS" \
  --population "$POPULATION" \
  --sigma "$SIGMA" \
  --workers "$WORKERS" \
  --strict-check-interval "$STRICT_CHECK_INTERVAL" \
  --regression-games "$REGRESSION_GAMES" \
  --definitive-require-positive-margin \
  --output-dir "$RUN_DIR" \
  --resume

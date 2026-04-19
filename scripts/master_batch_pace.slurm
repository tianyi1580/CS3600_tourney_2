#!/bin/bash
#SBATCH -J master-batch
#SBATCH --account=paceship-terratrends
#SBATCH -q inferno
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=24
#SBATCH --mem=32G
#SBATCH -t 12:00:00
#SBATCH -o logs/master_batch_%j.out
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=tma94@gatech.edu

# SLURM script to run master_batch.py on PACE.
# Usage: BOT_FIRST=v6 BOT_SECOND=v4_7_baseline GAMES=100 sbatch scripts/master_batch_pace.slurm

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}"
cd "$PROJECT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

export PYTHONUNBUFFERED=1

# Configuration via environment variables
BOT_FIRST="${yolanda_prime_v4_7:-}"
BOT_SECOND="${yolanda_prime_v6:-}"
GAMES="${GAMES:-100}"
PROFILE="${PROFILE:-strict}"
WORKERS="${WORKERS:-${SLURM_CPUS_PER_TASK:-24}}"

if [[ -z "$BOT_FIRST" || -z "$BOT_SECOND" ]]; then
  echo "Error: BOT_FIRST and BOT_SECOND environment variables must be set."
  echo "Example: BOT_FIRST=yolanda_prime_v6 BOT_SECOND=yolanda_prime_v4_7_baseline sbatch scripts/master_batch_pace.slurm"
  exit 1
fi

mkdir -p logs

echo "Starting Master Batch Matchup..."
echo "Bot 1: $BOT_FIRST"
echo "Bot 2: $BOT_SECOND"
echo "Games: $GAMES"
echo "Workers: $WORKERS"
echo "Profile: $PROFILE"
echo "----------------------------------------"

"$PYTHON_BIN" workflows/master_batch.py \
  "$BOT_FIRST" \
  "$BOT_SECOND" \
  --games "$GAMES" \
  --profile "$PROFILE" \
  --parallel \
  --workers "$WORKERS" \
  --quiet

echo "----------------------------------------"
echo "Master Batch Matchup Complete."

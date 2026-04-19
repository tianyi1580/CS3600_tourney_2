#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
PYTHON="${VENV_DIR}/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  echo "ERROR: expected venv at ${VENV_DIR}; run validate_m0.sh first or create .venv"
  exit 2
fi

echo "=== M1: unittest ==="
env PYTHONPATH="engine:3600-agents" "${PYTHON}" -m unittest discover -s tests -p 'test_*.py' -v

echo "=== M1: quality_guard ==="
"${PYTHON}" workflows/quality_guard.py

if [[ ! -f "${ROOT_DIR}/docs/m1_belief_correctness_report.md" ]]; then
  echo "ERROR: missing m1_belief_correctness_report.md"
  exit 1
fi

echo "=== M1: smoke (Yolanda self-play) ==="
env PYTHONPATH="engine:3600-agents" "${PYTHON}" engine/run_local_agents.py Yolanda Yolanda

echo "=== M1: search-precision batch (4 games, fast) ==="
"${PYTHON}" workflows/m1_search_precision_batch.py --games 4 --seed-start 0

echo "M1 validate_m1.sh completed successfully."

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
PYTHON="${VENV_DIR}/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  echo "ERROR: expected venv at ${VENV_DIR}; run validate_m0.sh first or create .venv"
  exit 2
fi

echo "=== M2: unittest ==="
env PYTHONPATH="engine:3600-agents" "${PYTHON}" -m unittest discover -s tests -p 'test_*.py' -v

echo "=== M2: quality_guard ==="
"${PYTHON}" workflows/quality_guard.py

if [[ ! -f "${ROOT_DIR}/docs/m2_time_manager_profiling_report.md" ]]; then
  echo "ERROR: missing m2_time_manager_profiling_report.md"
  exit 1
fi
if [[ ! -f "${ROOT_DIR}/docs/m2_tactical_ab_summary.md" ]]; then
  echo "ERROR: missing m2_tactical_ab_summary.md"
  exit 1
fi

echo "=== M2: competitive batch (CI-friendly N=2, strict, quiet) ==="
"${PYTHON}" workflows/m2_competitive_batch.py --games 2 --quiet --profile strict --seed-start 42

echo "validate_m2.sh completed successfully."

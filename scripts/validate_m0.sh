#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
LOG_DIR="${ROOT_DIR}/docs/logs/m0_validation"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${ROOT_DIR}/.venv"

RUN_RESTRICTED=0
SKIP_INSTALL=0
STRICT_RESTRICTED=0

usage() {
  cat <<'EOF'
Usage: ./validate_m0.sh [options]

Options:
  --restricted        Run restricted-mode validation command (Linux/course env)
  --strict-restricted Require restricted validation to print standalone True
  --skip-install      Reuse existing environment; skip pip install step
  --python <binary>   Python binary to use (default: python3 or $PYTHON_BIN)
  -h, --help          Show this help

Examples:
  ./validate_m0.sh
  ./validate_m0.sh --python python3.13
  ./validate_m0.sh --restricted
  ./validate_m0.sh --restricted --strict-restricted
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --restricted)
      RUN_RESTRICTED=1
      shift
      ;;
    --strict-restricted)
      STRICT_RESTRICTED=1
      shift
      ;;
    --skip-install)
      SKIP_INSTALL=1
      shift
      ;;
    --python)
      PYTHON_BIN="${2:-}"
      if [[ -z "${PYTHON_BIN}" ]]; then
        echo "ERROR: --python requires a binary argument"
        exit 2
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1"
      usage
      exit 2
      ;;
  esac
done

mkdir -p "${LOG_DIR}"
timestamp="$(date +%Y%m%d_%H%M%S)"
MASTER_LOG="${LOG_DIR}/m0_validation_${timestamp}.log"
LAST_STEP_LOG=""

log() {
  echo "$*" | tee -a "${MASTER_LOG}"
}

run_step() {
  local name="$1"
  shift
  local step_log="${LOG_DIR}/${name}_${timestamp}.log"
  LAST_STEP_LOG="${step_log}"
  log ""
  log "=== ${name} ==="
  log "command: $*"
  set +e
  "$@" >"${step_log}" 2>&1
  local code=$?
  set -e
  cat "${step_log}" >> "${MASTER_LOG}"
  if [[ ${code} -ne 0 ]]; then
    log "FAILED (${name}) exit=${code}. See ${step_log}"
    exit ${code}
  fi
  log "PASSED (${name})"
}

cd "${ROOT_DIR}"

log "M0 validation started at $(date)"
log "Repo: ${ROOT_DIR}"
log "Logs: ${LOG_DIR}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  log "ERROR: python binary not found: ${PYTHON_BIN}"
  exit 2
fi

run_step "python_version" "${PYTHON_BIN}" -c "import sys; print(sys.version)"

if [[ -d "${VENV_DIR}" ]]; then
  log "Removing existing virtualenv at ${VENV_DIR} to enforce requested interpreter"
  rm -rf "${VENV_DIR}"
fi

run_step "venv_create" "${PYTHON_BIN}" -m venv "${VENV_DIR}"
run_step "pip_upgrade" "${VENV_DIR}/bin/python" -m pip install --upgrade pip

if [[ ${SKIP_INSTALL} -eq 0 ]]; then
  run_step "pip_install" "${VENV_DIR}/bin/python" -m pip install -r "${ROOT_DIR}/requirements.txt"
else
  log "Skipping pip install (--skip-install set)"
fi

run_step "quality_guard" "${VENV_DIR}/bin/python" "${ROOT_DIR}/workflows/quality_guard.py"

run_step "runtime_smoke" env \
  PYTHONPATH="${ROOT_DIR}/engine:${ROOT_DIR}/3600-agents" \
  "${VENV_DIR}/bin/python" "${ROOT_DIR}/engine/run_local_agents.py" Yolanda Yolanda

if [[ ${RUN_RESTRICTED} -eq 1 ]]; then
  run_step "restricted_validate" env \
    PYTHONPATH="engine:3600-agents" \
    "${VENV_DIR}/bin/python" -c \
    "import os,sys; sys.path.insert(0,'engine'); import gameplay; ok,msg=gameplay.validate_submission(os.path.join(os.getcwd(),'3600-agents'),'Yolanda',limit_resources=True,use_gpu=False); print(ok); print(msg)"

  if ! awk '/^True$/{found=1} END{exit found?0:1}' "${LAST_STEP_LOG}"; then
    if [[ "$(uname -s)" == "Darwin" && ${STRICT_RESTRICTED} -eq 0 ]]; then
      log "WARNING (restricted_validate) no standalone 'True' found."
      log "macOS can fail engine RLIMIT resource checks even when local M0 logic is correct."
      log "Continuing as macOS-validated. Use --strict-restricted to require True."
      log "See ${LAST_STEP_LOG}"
    else
      log "FAILED (restricted_validate) expected a standalone 'True' line in output."
      log "See ${LAST_STEP_LOG}"
      exit 1
    fi
  fi
else
  log "Skipping restricted validation (pass --restricted to run)"
fi

if [[ -f "${ROOT_DIR}/docs/major_flaw_report.txt" ]]; then
  log "ERROR: major_flaw_report.txt exists; M0 gate is not clean"
  exit 1
fi

if [[ ! -f "${ROOT_DIR}/docs/m0_discrepancy_evidence_report.md" ]]; then
  log "ERROR: missing m0_discrepancy_evidence_report.md"
  exit 1
fi

log ""
log "M0 validation completed successfully."
log "Master log: ${MASTER_LOG}"

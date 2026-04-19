# quality_guard workflow (v4-aligned)

This workflow is a deterministic pass/fail gate for changes in this repository.
Ground truth precedence: `assignment_spec.md` first, then `bot_plan_v4.md`.

## Execution

Run:

```bash
.venv/bin/python workflows/quality_guard.py
```

For full M0 sign-off, prefer the repo helper:

```bash
./validate_m0.sh --python python3.13 --restricted
```

Full sign-off requires:
- successful dependency install
- clean `quality_guard`
- passing local runtime smoke
- restricted validation output containing a standalone `True` line

macOS behavior:
- Restricted validation may fail due OS-level RLIMIT behavior unrelated to agent logic.
- `validate_m0.sh` treats this as a warning on macOS by default.
- Use `--strict-restricted` to force strict `True` output checking on any OS.

Recommended setup:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Artifacts written at repo root:
- `major_flaw_report.txt` when any critical gate fails.
- `next_steps_suggestion.txt` when all critical gates pass.
- `m0_discrepancy_evidence_report.md` on every run (pass or fail), summarizing M0 evidence coverage.

## Gate Order

1. **Spec Lock Check**
- Verify `assignment_spec.md` and `bot_plan_v4.md` exist.
- Verify tests reference required v4 topics:
  - search inclusion hazard (`exclude_search=True` default)
  - tri-state parsing (`True/False/None`)
  - belief reset parity
  - timing fallback/emergency budget behavior
- Verify required behavioral test cases exist by function name in contract suites (not only token presence).

2. **Lint / Static Hygiene**
- Run `ruff check 3600-agents engine workflows tests` if `ruff` is available.
- Fallback: `python3 -m compileall 3600-agents engine workflows tests`.

3. **Unit + Contract Tests**
- Run: `python3 -m unittest discover -s tests -p "test_*.py"`.
- Includes checks for legality, search inclusion, tri-state parsing, belief normalization/reset, and timing fallback behavior.

4. **Coverage Gate (Balanced Mode)**
- Enforce `>=85%` total coverage on core modules:
  - `Yolanda.agent`
  - `Yolanda.belief`
  - `Yolanda.policy`
  - `Yolanda.runtime_state`
  - `Yolanda.time_manager`
- If coverage tooling is unavailable, this is a critical failure.

5. **Architecture Constraints**
- `agent.py` must orchestrate and delegate (not contain scoring/belief implementation internals).
- `belief.py` must expose: `predict`, `update`, `reset_after_capture`, `topk`.
- `policy.py` must expose: `generate_candidates`, `score_non_search`, `score_search`, `select_action`.
- Explicit search path must exist (`Move.search(...)` or equivalent explicit include path).
- `RuntimeState` must include normalization stats + fallback cache + opponent profiling counters.
- Reject network imports (`socket`, `requests`, `urllib`) in agent package.

6. **Runtime Readiness Smoke**
- Local smoke: `python3 engine/run_local_agents.py Yolanda Yolanda`.
- Restricted-mode smoke on Linux via `validate_submission(..., limit_resources=True)`.
- Non-Linux hosts log a warning and skip restricted seccomp smoke.
- In sandboxed environments, psutil process-list permission limits may downgrade runtime smoke to warnings.

7. **Reporting and Promotion Rule**
- Any critical failure -> write `major_flaw_report.txt` and block milestone progression.
- Full pass -> write `next_steps_suggestion.txt` with the next recommended milestone move.

## Promotion Policy

Do not advance milestone phases unless quality_guard is clean. Reliability and correctness gates are higher priority than optimization outcomes.

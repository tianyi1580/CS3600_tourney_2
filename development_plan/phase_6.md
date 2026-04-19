## Objective
Finalize M2 evaluation and quality controls required for M2->M3 promotion.

## Success Criteria
- Quality guard enforces lint/static, tests, coverage, architecture, and runtime-smoke stages.
- M2 profiling evidence exists for strict_240 and local_360 behavior.
- Tactical A/B summary artifact is generated.

## Task List
- Harden `quality_guard.py` for deterministic behavior and host-constraint reporting.
- Run and document strict/local profiling batches; record reliability and timeout behavior.
- Create `development_plan/artifacts/m2_profile_report.md` and `development_plan/artifacts/m2_tactical_ablation.md`.

## Verification
- `python3 workflows/quality_guard.py`
- `python3 -m unittest discover -s tests -p "test_*.py"`

## Timebox
3.5h

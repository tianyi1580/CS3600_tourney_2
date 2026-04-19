## Objective
Close M3 gates with mandatory scenario suite and regression evidence.

## Success Criteria
- Mandatory scenario tests required before M3 promotion are implemented and green.
- Regression gates confirm no reliability regression versus accepted M2 baseline.
- M3 artifact reports are generated.

## Task List
- Implement scenario tests for search inclusion, tri-state parsing, simulation fidelity parity, timeout edges, and runtime-mode readiness.
- Run regression comparisons vs M2 baseline metrics.
- Create `development_plan/artifacts/m3_clamp_verification.md` and `development_plan/artifacts/m3_elo_uplift.md`.

## Verification
- `python3 -m unittest discover -s tests -p "test_*.py"`
- `python3 workflows/quality_guard.py`

## Timebox
3.5h

## Objective
Lock M0 discrepancy correctness coverage against high-risk engine nuances from §9.

## Success Criteria
- Discrepancy tests cover search scoring location, constructor/play time semantics, and invalid-search prevention.
- Perspective and bookkeeping behavior are validated where relevant to policy internals.
- M0 evidence report is generated.

## Task List
- Extend tests for: search scoring in gameplay loop vs `Board.apply_move`, constructor budget semantics, and search legality guarantees.
- Add tests/assertions for perspective-safe bookkeeping assumptions used by policy.
- Create `development_plan/artifacts/m0_discrepancy_evidence.md` summarizing covered discrepancy rows and results.

## Verification
- `python3 -m unittest discover -s tests -p "test_*.py"`
- `python3 workflows/quality_guard.py`

## Timebox
4.0h

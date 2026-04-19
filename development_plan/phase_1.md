## Objective
Complete M0 correctness foundation for legal action generation and search inclusion safety.

## Success Criteria
- Candidate generation includes explicit search path and never depends on default `exclude_search=True` behavior.
- Tri-state parsing utility handles `True`/`False`/`None` safely.
- Fallback path always returns a legal action.

## Task List
- Implement/validate explicit search candidate construction in policy generation.
- Implement/validate tri-state channel parser and safe channel application.
- Add legality-preserving fallback order for low-time/error conditions.
- Add tests for search inclusion hazard and tri-state parsing behavior.

## Verification
- `python3 -m unittest tests/test_policy_contract.py`
- `python3 -m unittest tests/test_discrepancy_contract.py`
- `python3 workflows/quality_guard.py`

## Timebox
3.5h

## Objective
Implement M4 elite optional layer (anytime planner and cache/tuning scaffolding) without violating reliability gates.

## Success Criteria
- Anytime planner path is integrated behind strict timing guards.
- Optional state-feature caching exists and is bounded/safe.
- Reliability thresholds remain non-regressing under strict_240.

## Task List
- Add planner wrapper with hard interruption and fallback compatibility.
- Add bounded cache hooks for recurring state features.
- Add tests for planner timeout behavior and fallback correctness under interruption.

## Verification
- `python3 -m unittest discover -s tests -p "test_*.py"`
- `python3 workflows/quality_guard.py`

## Timebox
4.0h

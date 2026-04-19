## Objective
Implement M3 adaptive competitive upgrade with bounded opponent modeling.

## Success Criteria
- Opponent profile features are tracked and updated deterministically.
- Confidence-weighted adaptation and per-parameter clamps are enforced.
- Absolute coefficient envelopes are enforced after adaptation.

## Task List
- Implement adaptation cadence, confidence calculation, and delta clamping.
- Add envelope enforcement and low-confidence disable logic.
- Add tests for clamp invariants and adaptation stability under long traces.

## Verification
- `python3 -m unittest discover -s tests -p "test_*.py"`
- `python3 workflows/quality_guard.py`

## Timebox
4.0h

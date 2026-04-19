## Objective
Implement M2 tactical competitive core with v4 policy constants and hard-stop time safety.

## Success Criteria
- Tactical scorer contains v4-aligned components (`immediate`, `position`, `carpet_setup`, `denial`, `risk`).
- Time manager enforces emergency floor, phase multipliers/caps, and anti-burn guard.
- Fallback chain is active and deterministic.

## Task List
- Implement/validate tactical scoring composition and deterministic action ranking.
- Implement/validate strict_240/local_360 budget profile logic and emergency handling.
- Add tests for timeout-edge behavior, allocation invariants, and fallback determinism.

## Verification
- `python3 -m unittest tests/test_time_manager.py`
- `python3 -m unittest discover -s tests -p "test_*.py"`
- `python3 workflows/quality_guard.py`

## Timebox
4.0h

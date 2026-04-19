## Objective
Establish repository scaffolding, module boundaries, and the quality-gate framework required for v4 execution.

## Success Criteria
- `Yolanda` package structure and module ownership match v4 implementation contract.
- Test scaffolding exists for contract, discrepancy, belief, policy, and time manager checks.
- `workflows/quality_guard.md` and `workflows/quality_guard.py` are present and runnable.

## Task List
- Confirm/create module layout: `agent.py`, `belief.py`, `policy.py`, `runtime_state.py`, `time_manager.py`, `__init__.py`.
- Confirm/create baseline test layout in `tests/` with shared setup helpers.
- Refactor quality guard into deterministic stage gates with artifact outputs.
- Add report directories for phase evidence under `development_plan/artifacts/`.

## Verification
- `python3 -m compileall 3600-agents/Yolanda workflows tests`
- `python3 -m unittest discover -s tests -p "test_*.py"`
- `python3 workflows/quality_guard.py`

## Timebox
3.0h

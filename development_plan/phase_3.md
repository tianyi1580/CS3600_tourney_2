## Objective
Implement M1 belief core with transition prediction, observation update, and capture reset parity.

## Success Criteria
- Belief remains normalized and non-negative after predict/update cycles.
- Capture reset uses cached post-spawn prior semantics derived from runtime matrix.
- Top-k extraction is deterministic and usable by policy search generation.

## Task List
- Implement/validate `BeliefEngine.predict()`, `update(noise, dist, board)`, `reset_after_capture()`, `topk(k)`.
- Ensure constructor-provided transition matrix is canonical and normalized defensively.
- Add/expand tests for normalization, reset parity, and top-k determinism.

## Verification
- `python3 -m unittest tests/test_belief_engine.py`
- `python3 -m unittest discover -s tests -p "test_*.py"`

## Timebox
4.0h

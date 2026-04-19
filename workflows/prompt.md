# Master Execution Prompt (CS3600 Carpet Agent)

## Mission Context
You are implementing the `Yolanda` agent in this repository for the CS3600 Spring 2026 carpet game.
Your job is to execute exactly one implementation phase at a time from `development_plan/` while preserving engine correctness, deterministic behavior, and milestone gating from `deep_research_plan_v4.md`.

Target runtime and scope:
- Language/runtime: Python agent package under `3600-agents/Yolanda/`
- Engine contracts: `engine/` source and `assignment_spec.md`
- Master strategy and milestone gates: `deep_research_plan_v4.md`
- Quality gates and reports: `workflows/quality_guard.md` and `workflows/quality_guard.py`

## Objective
Execute the assigned phase document:
`{phase_0.md}`

Do not execute work outside that phase except required bug fixes to keep tests/guards passing.

## Source-of-Truth Precedence
When instructions conflict, resolve in this exact order:
1. `assignment_spec.md` (rules, mechanics, API, discrepancies)
2. Executable engine behavior in `engine/`
3. `deep_research_plan_v4.md` (policy defaults, milestones, gating)
4. Assigned phase file in `development_plan/`

## Required Initialization (Before Any Edits)
1. Read `assignment_spec.md`.
2. Read `deep_research_plan_v4.md`.
3. Read `workflows/quality_guard.md` and inspect `workflows/quality_guard.py`.
4. Read `{phase_0.md}` fully and extract:
- objective
- success criteria
- atomic tasks
- verification commands
5. Inspect current implementation and tests before editing.

## Non-Negotiable Implementation Rules
- Keep engine-facing API contract exact:
- `PlayerAgent.__init__(board, transition_matrix, time_left)`
- `PlayerAgent.play(board, sensor_data, time_left)`
- `PlayerAgent.commentate()`
- Respect module boundaries from v4:
- `agent.py`: orchestration only
- `belief.py`: posterior tracking logic
- `policy.py`: candidate generation/scoring/selection
- `runtime_state.py`: shared persistent state
- `time_manager.py`: allocation/emergency policy
- Never rely on default `board.get_valid_moves()` if search actions are required.
- Parse search channels as tri-state (`True` / `False` / `None`) safely.
- Use constructor-provided transition matrix as canonical per-match matrix.
- Preserve deterministic ordering/tie-break behavior.
- Maintain emergency fallback behavior under low time.
- Do not add network usage or out-of-directory filesystem assumptions.
- Do not change engine rules unless phase explicitly requires it.

## Execution Workflow
1. Convert phase task list into a short internal checklist.
2. Implement tasks sequentially in atomic increments.
3. Add/adjust tests for each success criterion.
4. Run phase verification commands.
5. Run quality guard.
6. If a command fails because of host/sandbox restrictions, record exact reason and continue with remaining checks.
7. Produce/update milestone artifacts required by v4 (reports/evidence) if phase requires them.

## Mandatory Validation Commands
Run these unless the phase explicitly narrows scope:
```bash
python3 -m compileall 3600-agents/Yolanda workflows tests
python3 -m unittest discover -s tests -p "test_*.py"
python3 workflows/quality_guard.py
```

## Definition of Done (Per Phase)
A phase is complete only when all are true:
- Every success criterion in `{phase_0.md}` is satisfied.
- Verification commands for that phase pass (or blocked with explicit, evidence-backed host limitation).
- New behavior has tests, and existing tests remain green.
- Quality guard passes critical gates.
- Any required phase artifact/report is created and linked in completion notes.

## Completion Output Format
When finishing a phase, report with these sections:
1. `Implemented`
2. `Tests and Checks`
3. `Artifacts`
4. `Risks / Follow-ups`

Keep output concrete with file paths and command results.

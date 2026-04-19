# assignment_spec.md

## High Level Overview
This is the game I am building a bot for. remember it. don't edit any code 
Basics
Each agent controls a worker on an 8x8 chessboard. The agents take turns making moves. After both have had 40 turns, the game is terminated.

Each agent gets a total of 4 minutes to come up with all its moves. If a player runs out of time, they lose the game.

The agent with the most points when the game terminates is the winner. Points are earned through:

Priming: When you paint a square with glue, you gain 1 point.
Carpeting: When you carpet a line of n primed squares, you gain points per the table below. Either player can step into a carpeted square.
| n | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 
|--------|----|---|---|---|----|----|----| 
| Points | -1 | 2 | 4 | 6 | 10 | 15 | 21 |

Catching the Rat: If you guess the square where the rat is hidden, you gain 4 points. If you guess incorrectly, you lose 2 points.
Start
Each corner of the map will have blocked squares randomly arranged in either a 3x2, 2x3, or 2x2 rectangle.

Player A moves first. Player B moves second. Both players spawn within the center 4x4 squares in horizontally mirrored positions.

There is a rat hidden in one of the squares.

You are given a 64x64 transition matrix where each cell (x, y) is mapped to a flat index i = y * 8 + x. The matrix defines the rat's movement probabilities:

T(i, j) = P(moving from cell i to cell j)

For any given i, only five entries can be non-zero (the rat staying in place or moving to one of the four adjacent cardinal neighbors), and probabilities always sum to 1.0. The rat can move under blocked squares.

The T table is different for every game but stays constant for the whole game.

Rat headstart: The rat is placed in square (0,0) and moves freely for 1000 moves (following the T table) before the game begins.

Play
Each turn, the agent either:

picks a move to perform, or
guesses the location of the rat.
Two workers cannot occupy the same square.

Move Types
Plain Step — Simply changes the worker's position in one of the four cardinal directions. You cannot plain step onto a primed square.
Prime Step — Can only happen on a square that is not primed or carpeted. When the worker departs the square, it becomes primed. You cannot prime step onto a primed square.
Carpet Roll of length k — Moves the worker in a straight line over k contiguous primed squares, starting from a square adjacent to the worker's current position, carpeting each square. The worker ends on the k-th (final) square.
Search Move
The worker searches any cell on the map for the rat (the worker itself does not move).

If the rat is found: +4 points
If the rat is not found: −2 points
The Rat
There is always a rat under the floor of one of the squares.

Before each turn, the rat moves one square in one of the cardinal directions (or stays) according to the T table and makes a noise.

Rat Noises
The rat can make the following noises: squeak, scratch, squeal. The probability depends on the floor type:

| Floor Type | Squeak | Scratch | Squeal | 
|------------|--------|---------|--------| 
| Blocked | 0.5 | 0.3 | 0.2 | 
| Space | 0.7 | 0.15 | 0.15 | 
| Primed | 0.1 | 0.8 | 0.1 | 
| Carpet | 0.1 | 0.1 | 0.8 |

Distance Estimate
On your worker's turn, it will hear the rat and receive an estimated Manhattan distance to the rat's square. The distance estimate is noisy:

| Reported Measure | Probability | |--------------------------|-------------| | One less than actual | 0.12 | | Correct | 0.70 | | One more than actual | 0.12 | | Two more than actual | 0.06 |

Your worker will never estimate less than zero. (If the dice roll would produce a negative estimate, you receive an estimate of zero.)

Rat Respawn
As soon as the rat is captured, a new rat is spawned and allowed to run for 1000 steps before the next player is given a turn.

If your opponent guesses on their turn, you will be told what they guessed and whether they were right or not.

Termination Conditions
The game ends under the following conditions:

A worker makes an invalid move → the responsible agent loses.
An agent runs out of time → that agent loses.
Both agents have made all their moves → the worker with the most points wins.

## 1) Document Metadata

| Field | Value |
| --- | --- |
| Document purpose | Canonical, AI-agent-readable specification for CS3600 Spring 2026 carpet game assignment and this repository's runtime behavior |
| Primary source documents | `assignment.pdf` (10 pages), `engine/` source code, `3600-agents/` sample agent |
| Generated from repo | `/Users/tianyima/Downloads/dist` |
| Extraction timestamp (local) | 2026-04-02 America/New_York |
| Audience | Human developers, coding agents, evaluators |
| Scope | Assignment rules, local runner mechanics, agent API contracts, practical implementation details |
| Precedence policy | For this repository runtime: **engine behavior is authoritative** when assignment PDF text and executable code differ |

### Deterministic parsing conventions used in this document

- Coordinates are `(x, y)` with `(0, 0)` at the upper-left corner.
- Flat index mapping is `i = y * 8 + x`.
- "Player" means the current agent from the board's current perspective (`board.player_worker`).
- "Enemy" means the opponent from current perspective (`board.opponent_worker`).
- Constants and enums are given using code names where available.

---

## 2) Canonical Assignment Rules (From PDF)

This section encodes the assignment PDF text as structured rules.

### 2.1 Core game structure

- Board size: `8 x 8`.
- Two workers alternate turns.
- Player A moves first.
- Each side has up to `40` turns.
- Match ends after both have taken all turns, or earlier on invalid move/timeout.

### 2.2 Time budget

- Each agent receives a **total** budget of `4 minutes` (`240` seconds) across all turns.
- Running out of total time causes immediate loss.

### 2.3 Scoring

| Action | Outcome |
| --- | --- |
| Prime step (paint current square with glue) | `+1` point |
| Carpet roll of length `n` | Uses carpet table below |
| Correct rat search guess | `+4` points |
| Incorrect rat search guess | `-2` points |

Carpet points table:

| `n` (roll length) | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| points | -1 | 2 | 4 | 6 | 10 | 15 | 21 |

### 2.4 Initial map and spawn

- Each corner gets a blocked rectangle shape randomly selected from:
  - `3x2`
  - `2x3`
  - `2x2`
- Both players spawn in the center `4x4` region.
- Spawn positions are horizontally mirrored.

### 2.5 Rat dynamics and transition matrix

- Rat occupies one board cell (hidden).
- Transition matrix `T` is `64 x 64`, where `T(i, j) = P(move from i to j)`.
- Allowed rat transitions per row are to:
  - stay in place
  - up/down/left/right cardinal neighbors
- Row probabilities sum to `1.0`.
- Off-board transitions have probability `0`.
- Rat can move "under" blocked squares.
- Rat starts from `(0, 0)`, then receives `1000` hidden headstart moves before gameplay.
- After a successful capture, new rat is spawned and again receives `1000` hidden moves.

### 2.6 Player turn action space

Each turn, agent chooses exactly one action:

1. Board move (`PLAIN`, `PRIME`, `CARPET`)
2. Search move (`SEARCH`) that guesses a rat location

Two workers cannot occupy same square.

#### 2.6.1 Plain step

- Move one cell in cardinal direction.
- Cannot plain-step onto primed square.
- Can plain-step onto carpeted square.

#### 2.6.2 Prime step

- Destination must be legal movement cell.
- Current square becomes primed when departing.
- Cannot prime-step if current square is already primed or carpeted.
- Cannot prime-step onto primed square.

#### 2.6.3 Carpet roll

- Choose direction and roll length `k`.
- Carpets `k` contiguous primed squares in a straight line starting adjacent to worker.
- Worker ends on the `k`-th carpeted square.

#### 2.6.4 Search move

- Worker does not move.
- Guess any cell.
- Correct: `+4`.
- Incorrect: `-2`.

### 2.7 Observation model per turn

Before each player turn:

1. Rat moves according to `T`.
2. Rat emits noise.
3. Current player receives:
   - noise category
   - noisy Manhattan distance estimate

Noise distribution by cell type:

| Cell type | Squeak | Scratch | Squeal |
| --- | --- | --- | --- |
| Blocked | 0.50 | 0.30 | 0.20 |
| Space | 0.70 | 0.15 | 0.15 |
| Primed | 0.10 | 0.80 | 0.10 |
| Carpet | 0.10 | 0.10 | 0.80 |

Distance measurement error model:

| Reported estimate relative to actual Manhattan distance | Probability |
| --- | --- |
| `actual - 1` | 0.12 |
| `actual` | 0.70 |
| `actual + 1` | 0.12 |
| `actual + 2` | 0.06 |

Distance lower bound:

- Reported estimate is clipped at `0` (never negative).

Opponent guess visibility:

- If opponent searched on their turn, you are informed of guessed square and whether it was correct.

### 2.8 Termination conditions

Match ends immediately when any of the following occurs:

- Invalid move by an agent -> that agent loses.
- Agent runs out of time -> that agent loses.
- Both agents complete all turns -> higher score wins (tie if equal).

### 2.9 Environment constraints (from PDF)

- Zip size limit: `<= 200 MB`.
- External code/data not created by team is forbidden.
- Network requests are forbidden.
- Agent may not read/write outside working directory.
- Target runtime: Python `3.12`, x86_64 Linux.
- Libraries listed in assignment include: `numpy`, `PyTorch`, `JAX`, `FLAX`, `Plyvel`, `Scikit-learn`.

### 2.10 Assignment development instructions

- Place bots under `3600-agents/<BotName>/agent.py`.
- Example local match command:
  - `python3 engine/run_local_agents.py Yolanda Yolanda`
- Match history JSON appears under `3600-agents/matches/` with names like `Yolanda_Yolanda_0.json`.
- Suggested workflow: keep project in shared git repository with teammate.
- Suggested housekeeping: add `matches/` artifacts to `.gitignore`.
- Report engine bugs to Ed Discussion.
- Multi-file package guidance:
  - include `__init__.py` and relative imports (example from assignment):
    - `from .agent import PlayerAgent`
    - `from . import rat_belief`
    - and in `agent.py`: `from .rat_belief import RatBelief`
- LLM policy from assignment:
  - LLM/coding-agent usage is allowed.
  - Teams are responsible for validating generated code.
  - Collaborating with people outside your team is not allowed.
- Infrastructure recommendation from assignment:
  - Build scripts for multi-game evaluation due stochastic maps and rat dynamics.
  - Parallel/batch evaluation is explicitly encouraged for tuning.
- Can utilize Georgia Tech's PACE for heavy compute workloads.

### 2.11 Submission flow (from PDF)

- Zip exactly the bot directory (for example, `Yolanda.zip` containing a folder with `agent.py`).
- Register and upload via `https://bytefight.org/Register`.
- 'Verify Code' email may land in spam.
- Create a team and add both teammates.
- Assignment requests using same email as official university records for credit matching.
- Upload zip and select scrimmage opponents on platform.

### 2.12 Grading/tournament statements in assignment

- Final cutoff stated: `11:59pm on April 19, 2026`.
- Ranking based on ELO.
- Final tournament ELO reset baseline is stated as `1500`.
- Reference bots and thresholds:
  - Above George: at least 70%.
  - Above Albert: at least 80%.
  - Above Carrie: at least 90%.
- Reference bot descriptions:
  - George: no-lookahead, extends primes and rolls carpet, opportunistic search.
  - Albert: expectiminimax with simple heuristic plus HMM rat tracking.
  - Carrie: Albert structure plus stronger cell-potential/distance heuristic.
- Within each grade pool (70-80, 80-90, 90-100), grading is scaled by ELO interpolation versus reference bots.
- Prize note: top team receives stated gift card and instructor lunch.

### 2.13 Appendix algorithms listed in assignment

The PDF includes concise recommendations (not mandatory rules):

- Minimax:
  - Recursive max/min on game tree.
  - Evaluate leaf states with heuristic.
  - Assignment calls out optimizations: alpha-beta, move ordering, iterative deepening, transposition tables.
- Expectiminimax:
  - Minimax with chance nodes using expected utility over stochastic outcomes.
- Monte Carlo Tree Search:
  - Four-step loop: selection, expansion, simulation, backpropagation.
- AlphaZero-style approach:
  - Neural policy/value estimates guide MCTS.
  - Trained through self-play.
  - Assignment notes substantial data/compute requirements.
- Hidden Markov Models:
  - Track hidden rat state via repeated predict/update on transition and observation models.

---

## 3) Engine API Contract

This section specifies concrete interfaces implemented by this codebase.

### 3.1 Player agent required class and methods

From sample agent and runtime invocation:

```python
class PlayerAgent:
    def __init__(self, board, transition_matrix=None, time_left: Callable = None):
        ...

    def play(self, board: board.Board, sensor_data: Tuple, time_left: Callable):
        return move.Move(...)

    def commentate(self) -> str:
        return ""
```

- Constructor is called once after process init.
- Constructor receives the per-match transition matrix (same matrix for both players in that game), as a JAX-compatible `64 x 64` float array.
- In constructor, `time_left()` tracks constructor budget (`10s` in resource-limited mode, `20s` in local default mode), not total game budget.
- `play(...)` is called every turn.
- `commentate()` is optional in spirit but runtime calls it at end and tolerates failure.

Primary references:

- `3600-agents/Yolanda/agent.py:14-33`
- `engine/player_process.py:324`, `engine/player_process.py:280-282`, `engine/player_process.py:343-355`
- `engine/gameplay.py:250`, `engine/gameplay.py:337-345`, `engine/gameplay.py:232-239`

### 3.2 Inputs passed to `play(...)`

`play(board, sensor_data, time_left)` receives:

- `board`: perspective-specific snapshot (`game_board.get_copy(False)`) of current state.
- `sensor_data`: tuple `(noise, estimated_distance)`.
  - `noise` is enum `Noise` (`SQUEAK`, `SCRATCH`, `SQUEAL`).
  - `estimated_distance` is clipped non-negative integer.
- `time_left`: callable returning remaining **total game budget** for current player (seconds) at play-time.

References:

- `engine/player_process.py:434`, `engine/player_process.py:269`, `engine/player_process.py:276-282`
- `engine/game/rat.py:136-141`

### 3.3 Board object schema relevant to agents

Board fields available and meaningful:

- Metadata:
  - `turn_count`
  - `is_player_a_turn`
  - `winner` (`None` before termination; enum after winner set)
  - `win_reason` (created when `set_winner(...)` is called; do not assume presence mid-game)
  - `time_to_play`
- Workers:
  - `player_worker` (current actor from current perspective)
  - `opponent_worker`
- Cell bitmasks:
  - `_space_mask`, `_primed_mask`, `_carpet_mask`, `_blocked_mask`
- Search history channels:
  - `opponent_search: (loc_or_none, result_or_none)`
  - `player_search: (loc_or_none, result_or_none)`
  - Runtime note: second tuple value is initialized as `False`, but can become `None` on non-search turns because gameplay appends `(None, None)`.

References:

- `engine/game/board.py:37-71`
- search updates in `engine/gameplay.py:457-460`

### 3.4 Board methods expected for agent use

- `is_valid_move(move, enemy=False) -> bool`
- `get_valid_moves(enemy=False, exclude_search=True) -> list[Move]`
- `forecast_move(move, check_ok=True) -> Board | None`
- `apply_move(move, timer=0, check_ok=True) -> bool`
- `reverse_perspective() -> None`
- `get_cell(loc) -> Cell`
- `set_cell(loc, cell_type) -> None`
- `is_valid_cell(loc) -> bool`
- `is_cell_blocked(loc) -> bool`
- `is_cell_carpetable(loc) -> bool`

References:

- `engine/game/board.py:73-575`

### 3.5 Move representation

Factory constructors:

- `Move.plain(direction)`
- `Move.prime(direction)`
- `Move.carpet(direction, roll)`
- `Move.search(search_loc)`

Raw fields in each move object:

- `move_type`
- `direction`
- `roll_length`
- `search_loc`

Reference: `engine/game/move.py:3-78`

### 3.6 Enums and constants used by engine

From `engine/game/enums.py`:

| Symbol | Value |
| --- | --- |
| `MAX_TURNS_PER_PLAYER` | 40 |
| `BOARD_SIZE` | 8 |
| `ALLOWED_TIME` | 240 |
| `RAT_BONUS` | 4 |
| `RAT_PENALTY` | 2 |

`CARPET_POINTS_TABLE`:

| roll length | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| points | -1 | 2 | 4 | 6 | 10 | 15 | 21 |

Enums:

- `MoveType = {PLAIN, PRIME, CARPET, SEARCH}`
- `Cell = {SPACE, PRIMED, CARPET, BLOCKED}`
- `Noise = {SQUEAK, SCRATCH, SQUEAL}`
- `Direction = {UP, RIGHT, DOWN, LEFT}`
- `Result = {PLAYER, ENEMY, TIE, ERROR}`
- `ResultArbiter = {PLAYER_A, PLAYER_B, TIE, ERROR}`
- `WinReason = {POINTS, TIMEOUT, INVALID_TURN, CODE_CRASH, MEMORY_ERROR, FAILED_INIT}`

Reference: `engine/game/enums.py:4-73`

---

## 4) Turn Execution Timeline

This is the exact turn order in local runtime (`play_game`).

1. Initialize board, blocked corners, mirrored center spawns, and rat spawn (`1000` headstart).
2. Start player subprocesses and construct `PlayerAgent` for each.
3. Repeat until game over:
   1. Rat moves once (`rat.move()`).
   2. Sensor tuple sampled for current player (`rat.sample(board)`).
   3. Current player process receives copied board + sensor + current remaining time.
   4. Player returns `Move` and measured elapsed time.
   5. If move is missing, winner is set from timer sentinel:
      - `timer == -1` -> `CODE_CRASH` path (includes some timeout/error paths)
      - `timer == -2` -> `MEMORY_ERROR`
      - else -> `TIMEOUT`
   6. Else apply move with validation (`board.apply_move(move, timer=timer, check_ok=True)`).
   7. If invalid move, player loses.
   8. If move is `SEARCH`, compare with rat location and apply `+4/-2`; on success, respawn rat with new `1000`-step headstart.
      - Implementation nuance: this branch runs whenever move type is `SEARCH`, even if the search move was already marked invalid.
   9. Append search result into rolling two-turn deque (`(None, None)` on non-search turns).
   10. Record history (if enabled).
   11. If game not over: `board.reverse_perspective()`.
   12. After perspective swap, set:
       - `board.opponent_search = searches[-1]` (last turn)
       - `board.player_search = searches[-2]` (turn before last)
4. Re-map perspective-relative winner (`Result`) into absolute arbiter winner (`ResultArbiter`).
5. Request optional `commentate()` from both players.

References:

- Setup: `engine/gameplay.py:232-270`, `engine/gameplay.py:335-346`
- Turn core: `engine/gameplay.py:372-460`
- Winner mapping: `engine/gameplay.py:462-476`
- Commentary: `engine/gameplay.py:488-495`

---

## 5) Board/State Semantics

### 5.1 Bitboard model

Board stores four 64-bit masks:

- `_space_mask`
- `_primed_mask`
- `_carpet_mask`
- `_blocked_mask`

Index mapping:

- `bit_index = y * BOARD_SIZE + x`
- bit `0` => `(0,0)`
- bit `63` => `(7,7)`

References:

- `engine/game/board.py:44-52`, `engine/game/board.py:402-412`

### 5.2 Cell state invariants

`set_cell` clears target bit from all masks first, then sets exactly one mask.

Reference: `engine/game/board.py:491-507`

### 5.3 Move validity logic (engine truth)

#### Plain

- Next location must not be blocked by:
  - out-of-bounds
  - blocked square
  - primed square
  - either worker occupancy

References:

- `engine/game/board.py:94-97`, `engine/game/board.py:526-550`

#### Prime

- Destination must satisfy plain movement legality.
- Current square must be `SPACE` (not primed, not carpeted).

Reference: `engine/game/board.py:98-106`

#### Carpet

- `roll_length` must be in `[1, BOARD_SIZE - 1]` => `[1, 7]`.
- Every traversed cell along direction must be carpetable:
  - in bounds
  - currently primed
  - not occupied by either worker

References:

- `engine/game/board.py:108-120`, `engine/game/board.py:552-575`

#### Search

- Any valid board coordinate `(0..7, 0..7)`.

Reference: `engine/game/board.py:122-125`

### 5.4 Scoring logic by move application

- `PRIME`: set current cell to `PRIMED`, move, add `+1`.
- `CARPET`: convert traversed primed cells to carpet, move to last cell, add points from carpet table.
- `SEARCH`: scoring handled outside `Board.apply_move` by game runner.

References:

- `engine/game/board.py:243-258`
- `engine/gameplay.py:434-443`

### 5.5 Turn/accounting updates in `Board.end_turn`

When a move is applied:

- `turn_count += 1`
- `player_worker.turns_left -= 1`
- `player_worker.time_left -= timer`
- winner checked
- `is_player_a_turn` flipped

Reference: `engine/game/board.py:266-280`

### 5.6 Perspective behavior

- `reverse_perspective()` swaps `player_worker` and `opponent_worker` only.
- It does not rotate board coordinates or alter masks.

Reference: `engine/game/board.py:395-400`

### 5.7 Win detection behavior

`check_win` detects:

- timeout outcomes (including near-simultaneous timeout tie rule using `timeout_bounds=0.5`)
- points result after both turns exhausted or `turn_count >= 80`
- post-apply nuance in `play_game`: after `apply_move`, an extra `if board.player_worker.time_left <= 0` check can overwrite prior timeout tie decisions with `Result.ENEMY` timeout.

References: `engine/game/board.py:282-305`, `engine/gameplay.py:426-428`

### 5.8 Concrete examples

#### Example A: Prime legality

Given current player at `(3,3)`:

- If current cell is `SPACE` and destination `(3,2)` is unblocked/unprimed/unoccupied -> `Move.prime(Direction.UP)` valid.
- If current cell already `PRIMED` or `CARPET` -> same move invalid.

Rule source: `engine/game/board.py:98-106`

#### Example B: Carpet chain break

If primed cells to the right from `(2,2)` are:

- `(3,2)=PRIMED`, `(4,2)=SPACE`

Then:

- `Move.carpet(Direction.RIGHT, 1)` valid.
- `Move.carpet(Direction.RIGHT, 2)` invalid (second cell not carpetable).

Rule source: `engine/game/board.py:114-120`, `engine/game/board.py:187-191`

#### Example C: Search bookkeeping after perspective swap

Suppose Player A searched `(4,5)` and missed.

After A turn and before B turn:

- board perspective is reversed.
- From B's view:
  - `opponent_search == ((4,5), False)`
  - `player_search` is prior turn's search event.

Rule source: `engine/gameplay.py:445-460`

---

## 6) Rat Model Details

### 6.1 Transition matrix loading and mutation

Local runtime transition matrix pipeline:

1. Randomly choose one `.pkl` from `engine/transition_matrices/`.
2. Convert to JAX float32.
3. Apply element-wise multiplicative noise in range `[-10%, +10%]`.
4. Clamp negatives to `0`.
5. Renormalize each row to sum `1.0`.
6. Zero entries remain zero under this perturbation path (support pattern is preserved).

Reference: `engine/gameplay.py:10-30`

### 6.2 Matrix shape/data properties in this repo

Observed assets:

- `bigloop.pkl`
- `hloops.pkl`
- `quadloops.pkl`
- `twoloops.pkl`

All are `64 x 64`, with per-row nonzero count in `[3, 5]`, and row sums approximately `1.0` (floating-point epsilon) before runtime perturbation.

### 6.3 Rat spawn and movement

- `spawn()` sets rat to `(0,0)` then performs `1000` moves.
- `move()` samples from cumulative distribution of current row.

References:

- `engine/game/rat.py:6`, `engine/game/rat.py:127-131`, `engine/game/rat.py:83-101`

### 6.4 Noise model by tile type

| Tile type | `P(SQUEAK)` | `P(SCRATCH)` | `P(SQUEAL)` |
| --- | --- | --- | --- |
| `Cell.BLOCKED` | 0.50 | 0.30 | 0.20 |
| `Cell.SPACE` | 0.70 | 0.15 | 0.15 |
| `Cell.PRIMED` | 0.10 | 0.80 | 0.10 |
| `Cell.CARPET` | 0.10 | 0.10 | 0.80 |

Reference: `engine/game/rat.py:10-15`

### 6.5 Distance estimate model

- Actual metric: Manhattan distance.
- Offset distribution:
  - `-1` with `0.12`
  - `0` with `0.70`
  - `+1` with `0.12`
  - `+2` with `0.06`
- Final estimate clipped to minimum `0`.

References:

- `engine/game/rat.py:21-23`, `engine/game/rat.py:112-125`

---

## 7) Runtime and Sandbox Behavior

### 7.1 Process architecture

- Each agent runs in its own subprocess (`PlayerProcess`).
- Parent process communicates using multiprocessing queues.
- Board passed to agent methods is copied (`get_copy(False)`).

References:

- `engine/player_process.py:374-387`
- `engine/player_process.py:406-407`, `engine/player_process.py:434`

### 7.2 Timing and timeout handling

- Constructor and play are wrapped by timeout windows:
  - Constructor wait: `timeout + extra_ret_time`
  - Play wait: `timeout + extra_ret_time`
- In `play_game`:
  - `extra_ret_time = 5`
  - `init_timeout = 10` if resource-limited mode
  - `init_timeout = 20` in default local mode
- Per-turn allowed compute is current remaining time budget.

References:

- `engine/gameplay.py:233-238`
- `engine/player_process.py:398-443`

### 7.3 Memory and VRAM limits

In resource-limited mode (`limit_resources=True`):

- RAM soft/hard limit via `RLIMIT_RSS`:
  - `1536 MB`
- GPU VRAM check (if GPU enabled):
  - `4 GB`

References:

- `engine/player_process.py:166-215`
- `engine/player_process.py:183-205`

### 7.4 Seccomp and syscall restrictions (resource-limited mode)

When enabled, process applies seccomp rules that kill process on many classes of syscalls including:

- Networking (`socket`, `connect`, `send*`, `recv*`, etc.)
- Privilege and scheduling controls (`setuid`, `setgid`, `setpriority`, etc.)
- Exec and seccomp changes (`execve`, `execveat`, `seccomp`, `prctl`)
- Various filesystem and kernel operations

Reference: `engine/player_process.py:44-134`

### 7.5 Local runner defaults vs tournament-like mode

`run_local_agents.py` uses:

- `limit_resources=False`
- `display_game=True`
- `record=True`

This means local default does **not** enforce seccomp/resource constraints unless code path is changed.

References:

- `engine/run_local_agents.py:23-33`
- `engine/gameplay.py:236-239`, `engine/gameplay.py:274-280`

---

## 8) Codebase Map

### 8.1 Top-level layout

| Path | Responsibility |
| --- | --- |
| `assignment.pdf` | Official assignment text and grading/tournament guidance |
| `engine/` | Game engine, runtime, process sandboxing, board/rat logic |
| `3600-agents/` | Agent packages; includes sample `Yolanda` bot |
| `requirements.txt` | Local dependency manifest for this repo |

### 8.2 Engine subsystem map

| Path | Responsibility |
| --- | --- |
| `engine/gameplay.py` | Match orchestration, turn loop, move validation outcomes, scoring side effects for search, rat updates |
| `engine/player_process.py` | Agent subprocess lifecycle, timeout wrappers, memory checks, optional seccomp sandbox |
| `engine/run_local_agents.py` | Local CLI entrypoint to run two agents and write match JSON |
| `engine/board_utils.py` | Rendering helpers, spawn generation, history JSON serialization |
| `engine/transition_matrices/*.pkl` | Candidate rat transition matrices loaded per game |
| `engine/game/board.py` | Board state container, bitmask operations, move generation/validation/application |
| `engine/game/rat.py` | Rat movement and sensor model implementation |
| `engine/game/move.py` | Move object and constructors |
| `engine/game/enums.py` | Constants/enums for gameplay semantics |
| `engine/game/worker.py` | Worker state (position, score, turns, time) |
| `engine/game/history.py` | Turn history capture and replay metadata |
| `engine/game/__init__.py` | Package-level guidance and module exports |

### 8.3 Agent package map

| Path | Responsibility |
| --- | --- |
| `3600-agents/Yolanda/agent.py` | Minimal reference bot; random valid non-search move policy |

### 8.4 Local execution and outputs

- Run local match:
  - `python3 engine/run_local_agents.py <PlayerAName> <PlayerBName>`
- Output match history:
  - `3600-agents/matches/<PlayerA>_<PlayerB>_<index>.json`

Reference: `engine/run_local_agents.py:10-52`

---

## 9) Discrepancies and Nuances (Assignment vs Engine)

The table below captures important differences or subtle runtime truths.

| Topic | Assignment PDF statement | Engine behavior in this repo | Practical implication | Source references |
| --- | --- | --- | --- | --- |
| Total time budget | 4 minutes total per agent | `play_game` uses `240` only when `limit_resources=True`; default local path sets `360` | Local matches may overestimate available time compared to tournament rules | `assignment.pdf` p1, `engine/gameplay.py:232-239` |
| Search in move generation | Turn can be move or rat guess | `board.get_valid_moves()` defaults `exclude_search=True` | Bots using `get_valid_moves()` blindly will never search unless they pass `exclude_search=False` or build search moves manually | `assignment.pdf` p3, `engine/game/board.py:130`, `engine/game/board.py:193-195` |
| Transition matrix stability wording | `T` differs per game and is constant during game | Base `.pkl` chosen per game, then random +/-10% multiplicative perturbation applied once and fixed for that game | Good to treat provided `transition_matrix` as canonical per match, but do not assume it exactly equals stored `.pkl` values | `assignment.pdf` p2, `engine/gameplay.py:10-30` |
| Noise names in prose | PDF prose says noises "squeak, scratch" but table includes 3 categories | Engine has 3-category enum including `SQUEAL` and uses 3-way distributions | Agent logic must handle all three noise values | `assignment.pdf` p3, `engine/game/enums.py:31-35`, `engine/game/rat.py:10-15` |
| Search scoring location | Search described as a player action | `Board.apply_move` does not score search; gameplay loop handles +/- points and respawn | Simulations using `forecast_move/apply_move` alone must manually model search scoring and rat respawn | `assignment.pdf` p3-4, `engine/game/board.py:256-258`, `engine/gameplay.py:434-443` |
| Search tuple typing | PDF implies search-result bool semantics | Engine can publish `(None, None)` for non-search turns (after deque updates), not always `(None, False)` | Treat search result field as tri-state (`True`/`False`/`None`) in agent parsing | `assignment.pdf` p4, `engine/game/board.py:66-68`, `engine/gameplay.py:431-446`, `engine/gameplay.py:459-460` |
| Missing-move classification | PDF says timeout loses; crash behavior described generally | `run_timed_play` returns `(None, -1, "Timeout")` on queue wait timeout; gameplay maps `timer == -1` to `CODE_CRASH` | Some timeout-like failures are reported as code crash in local runtime | `engine/player_process.py:462-463`, `engine/gameplay.py:409-415` |
| Timeout tie handling | PDF only states timeout loses | `check_win` supports near-simultaneous timeout tie, but `play_game` post-apply check can overwrite with enemy-timeout outcome | In edge timing cases, final timeout result may differ from `check_win` tie logic | `engine/game/board.py:289-297`, `engine/gameplay.py:426-428` |
| Invalid search side effects | PDF invalid move rule implies immediate loss | Gameplay still executes search scoring block if move type is `SEARCH`, even after invalid-move loss is set | Invalid search can still mutate score (`-2` on miss) after game is already decided | `engine/gameplay.py:419-425`, `engine/gameplay.py:434-443` |
| Runtime restrictions | PDF describes restricted environment (no network, bounded environment) | Local runner default sets `limit_resources=False`, so seccomp restrictions are not applied locally by default | Passing local tests does not prove compatibility with tournament restrictions | `assignment.pdf` p4, `engine/run_local_agents.py:32`, `engine/player_process.py:210-219` |
| Constructor timeout policy | Not explicitly specified in PDF | Engine enforces constructor timeout (`10` or `20` seconds depending on mode) | Heavy initialization must fit constructor budget | `engine/gameplay.py:234-238`, `engine/player_process.py:398-429` |
| Opponent search reporting field text | PDF has a small typo in one bullet description | Engine maintains two rolling search channels (`opponent_search`, `player_search`) across turns after perspective swap | Use these fields directly as the implementation truth; do not rely on PDF typoed bullet text | `assignment.pdf` p4, `engine/game/board.py:66-68`, `engine/gameplay.py:445-460` |
| Winner representation | Human-readable A/B winner in assignment | Internal move loop computes perspective-relative winner (`Result`), then remaps to absolute (`ResultArbiter`) at end | If inspecting internals mid-game, be careful about perspective semantics | `assignment.pdf` p3-4, `engine/gameplay.py:462-476` |
| Worker default time constant | Assignment baseline implies 240 sec | `Worker` default is 240, but `Board` constructor can override and does in local default run | Always read `board.player_worker.time_left` instead of assuming fixed initial constant | `engine/game/worker.py:10`, `engine/game/board.py:59-60`, `engine/gameplay.py:232-239` |

### Reconciliation rule

For implementation against this repository:

1. Use assignment PDF for high-level competition intent.
2. Use engine source behavior for exact mechanics and API contract.
3. When conflicts exist, prioritize executable engine logic in this repo.

### 9.1 Audit coverage for this revision

This `assignment_spec.md` revision was validated against:

- `assignment.pdf` pages `1-10` (full extracted text review).
- Engine runtime files:
  - `engine/gameplay.py`
  - `engine/player_process.py`
  - `engine/board_utils.py`
  - `engine/run_local_agents.py`
  - `engine/game/*.py`
- Example agent: `3600-agents/Yolanda/agent.py`
- Dependency/runtime context: `requirements.txt`
- Transition assets: `engine/transition_matrices/*.pkl` (shape/support/row-sum sanity checks)

---

## 10) Implementation Checklist for Agents

Use this checklist to build robust agents compatible with both assignment intent and code reality.

### 10.1 Interface and lifecycle

- Implement class `PlayerAgent` with:
  - `__init__(board, transition_matrix, time_left)`
  - `play(board, sensor_data, time_left) -> Move`
  - optional `commentate() -> str`
- Ensure constructor completes inside strict timeout budget.
- In `__init__`, interpret `time_left()` as constructor budget; in `play`, interpret it as remaining total game budget.
- Keep constructor and play code resilient to exceptions.

### 10.2 Move generation and legality

- Do not rely on default `board.get_valid_moves()` alone if you want search actions.
- For rat guesses, either:
  - call `board.get_valid_moves(exclude_search=False)`, or
  - generate `Move.search((x, y))` manually.
- Validate custom-generated moves with `board.is_valid_move(move)` when uncertain.

### 10.3 Time management

- Treat `time_left()` as authoritative remaining total budget.
- Reserve safety buffer per turn for Python overhead and IPC latency.
- Use iterative deepening/time checks inside planning loops.

### 10.4 Belief tracking for rat

- Maintain posterior over 64 cells using:
  - transition matrix propagation each turn,
  - noise likelihood by tile type,
  - distance likelihood with offset model `{-1,0,+1,+2}` and clipping.
- On successful search, reset belief to `(0,0)` then apply 1000 transition steps (or equivalent matrix power update).

### 10.5 Perspective and state bookkeeping

- Remember incoming board is already from your side's perspective.
- Use `opponent_search`/`player_search` as turn-to-turn rat evidence, but parse result as tri-state (`True`, `False`, or `None`).
- Do not assume `board.win_reason` exists before game termination.
- If simulating opponents with `forecast_move/apply_move`, call `reverse_perspective()` intentionally where needed.

### 10.6 Search policy and score tradeoff

- Search expected value baseline:
  - `EV(search at cell c) = 4 * P(rat at c) - 2 * (1 - P(rat at c)) = 6*P(c) - 2`
- Positive EV threshold is `P(c) > 1/3` before strategic adjustments.
- Consider time, positional opportunities, and opponent score state before committing to search.

### 10.7 Robustness against runtime conditions

- Avoid network assumptions and unsafe filesystem behavior.
- Keep memory footprint controlled.
- Avoid depending on local non-sandbox defaults for tournament readiness.

### 10.8 Suggested local workflow

1. Start from sample package structure in `3600-agents/Yolanda/`.
2. Run self-play repeatedly:
   - `python3 engine/run_local_agents.py YourBot YourBot`
3. Run head-to-head variants to test stability under stochastic boards/rat transitions.
4. Parse generated match JSON for metric tracking and regression detection.

---

## Appendix A: Compact Reference Tables

### A.1 Constant table (assignment + engine-aligned)

| Name | Value | Meaning |
| --- | --- | --- |
| Board size | 8 | Cells per side |
| Turns per player | 40 | Max actions per side |
| Max total turns | 80 | Absolute match cap |
| Search reward | +4 | Correct rat guess |
| Search penalty | -2 | Incorrect rat guess |
| Prime reward | +1 | Prime step bonus |
| Rat headstart | 1000 | Steps before active play and after each capture |
| Carpet roll min | 1 | Minimum roll |
| Carpet roll max | 7 | Maximum roll on 8x8 |

### A.2 Carpeting score table

| Roll length `k` | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Score delta | -1 | 2 | 4 | 6 | 10 | 15 | 21 |

### A.3 Noise table

| Floor type | Squeak | Scratch | Squeal |
| --- | --- | --- | --- |
| Blocked | 0.50 | 0.30 | 0.20 |
| Space | 0.70 | 0.15 | 0.15 |
| Primed | 0.10 | 0.80 | 0.10 |
| Carpet | 0.10 | 0.10 | 0.80 |

### A.4 Distance error table

| Offset from actual Manhattan distance | Probability |
| --- | --- |
| -1 | 0.12 |
| 0 | 0.70 |
| +1 | 0.12 |
| +2 | 0.06 |

Lower bound clamp: reported distance `>= 0`.

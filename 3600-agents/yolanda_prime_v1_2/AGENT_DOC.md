# Yolanda Prime: Architectural & Strategic Deep-Dive

## 1. Executive Summary
`yolanda_prime` is an elite-tier competitive agent for the CS3600 Carpet Game. It utilizes a Hidden Markov Model (HMM) for rat tracking, a depth-limited adversarial Minimax search for tactical refinement, and a phase-dependent heuristic policy for global strategy. The version "Prime" represents the finalized, bug-fixed, and optimized evolution of the `yolanda_mitchell1.2` lineage.

## 2. Mathematical Models

### 2.1 Hidden Markov Model (Rat Tracking)
The `BeliefEngine` maintains a posterior probability distribution $P(X_t | e_{1:t})$ over the 64 board cells.
- **Prediction Step**: At the start of each turn, the belief is propagated through the transition matrix $T$ provided by the game environment: $B'(x_t) = \sum B(x_{t-1}) \cdot P(x_t | x_{t-1})$.
- **Update Step**: When sensor data (Noise $n$, Distance $d$) arrives, the belief is re-weighted using the sensor model $P(e_t | x_t)$.
- **Search Feedback**: If a search occurs at location $L$:
    - **Hit**: The belief at $L$ is set to 1.0, and all other cells are zeroed.
    - **Miss**: The belief at $L$ is set to 0.0, and the distribution is re-normalized.

### 2.2 Adversarial Minimax Search
The `Lookahead` engine performs a depth-limited search (typically 3-5 plies) using Alpha-Beta pruning.
- **Perspective Handling**: The engine uses `board.reverse_perspective()` to simulate the opponent's turn. 
- **Static Evaluator**: At leaf nodes, the bot calculates a **Point Differential Potential**:
  $$Score = (OwnPotentialPoints + 0.2 \cdot Mobility) - (OpponentPotentialPoints + 0.2 \cdot Mobility)$$
- **Stability Guard**: All perspective shifts are wrapped in `try...finally` blocks to ensure the board state is never left in a corrupted (reversed) state upon search timeout.

### 2.3 Rat Guessing Expected Value (EV)
The bot only executes a `SEARCH` action if the mathematical Expected Value exceeds the points of the best available movement:
$$EV_{search} = P(rat) \cdot 4 - (1 - P(rat)) \cdot 2 = 6 \cdot P(rat) - 2$$
In the opening phase, a "courage" margin is added to this threshold to prevent bleeding points to early-game uncertainty.

## 3. Component Architecture

### 3.1 Policy Engine (`strategy/policy.py`)
Ranks all legal moves using a weighted linear combination of heuristics:
- **Immediate Points**: Points from `PRIME` (1) or `CARPET` (Table-based).
- **Centrality**: Prefers the center $4 \times 4$ to maintain maximum board connectivity.
- **Chain Setup**: Uses `BoardAnalysis` to identify the longest possible carpet roll achievable from a target destination.
- **Denial/Sabotage**: Penalizes moves that leave the opponent with easy access to high-value primed chains.

### 3.2 Board Analysis (`strategy/board_analysis.py`)
Provides $O(1)$ spatial queries by pre-calculating snapshots of the board:
- **BFS Distance Matrices**: Shortest path distances from both workers to all walkable cells.
- **Connectivity Components**: Identifies if a carpet action will "bisect" the board (fragmentation penalty).
- **Chain Profiles**: Scans all directions from every cell to find primed chain lengths and entry points.

### 3.3 Time Manager (`infra/time_manager.py`)
- **Dynamic Allocation**: Allocates ~35% of remaining time per turn, scaling down as turns decrease.
- **Emergency Floor**: If total clock drops below 1.2s, the bot bypasses all calculation and returns the first legal move to prevent timeout disqualification.

## 4. Strategic Phases

| Phase | Turns | Primary Objective | Key Heuristic Bias |
| --- | --- | --- | --- |
| **Opening** | 1–12 | Spatial Control | High Centrality (2.5x), Aggressive Priming |
| **Middle** | 13–28 | Value Setup | Chain Completion (L5+), Opponent Sabotage |
| **Endgame** | 29–40 | Cash-Out | Carpet rolls (even L3), Aggressive Rat Search |

## 5. Performance & Stability
- **Crash Bug Fix**: Resolved the "Illegal Move" error caused by search-deadline perspective leakage.
- **Efficiency**: Optimized BFS kernels reduce per-turn overhead, allowing deeper Minimax plies (up to depth 5) within the 240s tournament limit.
- **Reliability**: Layered fallbacks ensure that even if heuristics fail, a valid (if sub-optimal) move is always returned.

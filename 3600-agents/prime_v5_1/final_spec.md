# Yolanda Prime v5.1 — Technical Specification & Design Philosophy

*“Don't play the odds, play the man.”*

---

## 1. Executive Summary: The Asymmetric Adversary
Yolanda Prime v5.1 is not a traditional board-game agent; it is an **Asymmetric Resource Allocator**. In a tournament environment with a strict 240s total match budget, the most precious resource is not points, but **CPU time**. 

### 1.1 Core Design Philosophy
The bot operates on a **"Return on Investment" (ROI)** principle. Most turns in a Yolanda match are tactically trivial (e.g., walking toward a known rat or extending a safe carpet). Spending 5 seconds searching a trivial turn is a strategic failure. Yolanda Prime identifies these "Low-Leverage" moments in milliseconds and "banks" its time for "High-Leverage" moments—turns where the rat belief is split across multiple quadrants or where a single move could decide a 10-point territory swing.

### 1.2 The Multi-Layered Architecture
To achieve this, the system is strictly decoupled into four functional layers:
1.  **The Brain (Tracking)**: A Hidden Markov Model (HMM) for probabilistic rat localization.
2.  **The Processor (Search)**: A Bitboard-optimized Alpha-Beta engine for deep tactical lookahead.
3.  **The Architect (Planning)**: A Dynamic Programming (DP) engine for macroscopic carpet paths.
4.  **The Strategist (Policy)**: A dynamic coordinator that adjusts heuristics and time based on game phase and opponent behavior.

---

## 2. System Architecture & Information Flow

### 2.1 Technical System Map
This map illustrates the internal dependencies and signal pathways between the modular components.

```text
[ BOARD ENGINE ] -> [ SENSOR DATA ] -> [ BELIEF ENGINE (HMM) ]
                                             |
                                             v
[ TIME MANAGER ] <--- [ COMPLEXITY SIGNALS ] <--- [ ORCHESTRATOR ]
      |                                      |           |
      v                                      v           |
[ SOFT/HARD DEADLINES ] <--- [ ALPHA-BETA BITBOARD SEARCH ]      |
                                 |          ^            |
                                 v          |            |
                        [ LEAF EVALUATOR ] <--- [ ADVERSARIAL OVERRIDES ]
                                 |          |
                        [ VORONOI MAP ] <--- [ CARPET PLANNER (DP) ]
                                 |
                                 v
                        [ SEARCH POLICY (GATE) ] ----> [ FINAL MOVE ]
```

### 2.2 Input-to-Output Data Graph
This graph defines the transformation of raw engine data into a concrete tactical action.

```text
INPUTS                          PIPELINE TRANSFORMATION                          OUTPUT
======                          =======================                          ======

Board Object ----+      +-----> [ 1. BELIEF UPDATE ] ----(Peak P / Entropy)---+
                 |      |                                                     |
Sensor Data -----+------+-----> [ 2. CARPET PLANNER] ----(Macro Move Hint)----+
                 |      |                                                     |
Time Left -------+      +-----> [ 3. TIME MANAGER  ] ----(Budget Allocation)--+
                                                              |               |
                                                              v               v
                        +-----> [ 4. ALPHA-BETA SEARCH ] <----+------- [ 5. SEARCH POLICY ]
                        |           (Depth 7-9 PVS)                       (Accuracy Gate)
                        |                 |                                   |
                        |                 v                                   v
                        +------- [ LEAF EVALUATION ]                 [ engine.Move Result ]
                                 (7-Term Heuristic)                  (SEARCH / tactical)
```

---

## 3. The Brain: HMM & Information Foraging
The **Belief Engine** maintains the "Ground Truth" of the rat's position. It is the most sophisticated component of the bot.

### 3.1 Advanced Sensor Fusion
- **Negative Information Extraction**: When an opponent searches and misses, the engine doesn't just record it. It zeroes out that cell in our belief vector and re-normalizes. This allows us to "see through the opponent's eyes."
- **Bayesian Smoothing**: We apply a $0.5\%$ uniform floor to all cells during normalization. This prevents "Belief Lock-In," where a single noisy sensor reading could otherwise convince the bot a cell is $0\%$ probable forever.
- **Multimodal Transitions**: The engine tracks the *type* of move the opponent made. If they used a `CARPET` (double-step), we apply the transition matrix $T$ twice ($T^2$). If they searched, we apply $T$ once.

### 3.2 Entropy-Driven Foraging
The bot measures the Shannon Entropy ($H$) of the belief vector.
- If $H_{norm} > 0.75$, the bot enters **Foraging Mode**. 
- It treats "Information Gain" as a currency. The heuristic engine adds an `epsilon` bonus for moving toward high-uncertainty cells, effectively sacrificing immediate points to "clear the map."

---

## 4. The Processor: Bitboard Alpha-Beta Search
To reach depths of 7-9 plies within seconds, Yolanda Prime abandons traditional Python objects in favor of **Bitboards**. The entire board state is represented as four 64-bit integers.

### 4.1 Principal Variation Search (PVS)
We assume the first move found (via move ordering) is the best. Subsequent moves are searched with a "Null Window" (a tiny range around Alpha). If the search returns a value outside that window, it proves our assumption was wrong, and we re-search that branch fully. This drastically increases pruning efficiency.

### 4.2 Null-Move Pruning (NMP)
The bot uses a "pass-the-turn" check. If we can skip our turn and the resulting score is *still* higher than the opponent's best possible score (Beta), we assume the position is so strong that we don't need to search it further. This "free" pruning typically grants an extra 2 plies of depth.

---

## 5. The Dynamic Heuristic Engine (Phase Separation)
The "Heuristic Soul" of the bot is not static. It shifts its weights (`alpha` through `omega`) based on the game's progression.

### 5.1 Strategic Phase Breakdown

| Phase | Turns | Tactical Focus | Heuristic Bias |
| :--- | :--- | :--- | :--- |
| **Opening** | 0-19 | **Information Gain** | **High Epsilon/Delta**: Prioritizes mobility and "scouting." The bot establishes a center-grid presence and reduces rat uncertainty. |
| **Mid-Game**| 20-59 | **Territory Dominance**| **High Beta/Gamma**: Focuses on "Voronoi Pushing." It uses the Carpet Planner to secure high-yield chains and boxes the opponent worker out of the center. |
| **End-Game**| 60-100| **Score Preservation** | **High Alpha/Omega**: Switches to "Precision Strike." It stops searching for information and focuses solely on the point-maximizing move. |

### 5.2 Forecast-Based Hotspots
Instead of moving to where the rat is *now*, we use the **Forecast Heuristic**:
```python
# Project the belief vector 3 turns (6 single-steps) into the future
forecast = belief @ (Transition_Matrix ** 6)
# Reward proximity to the peaks of the forecast
heuristic_score += weights['eta'] * forecast[candidate_pos]
```
This causes the bot to move to **interception points**, cutting the rat off before it even arrives.

---

## 6. Adversarial Modeling: The George Filter
Yolanda Prime v5.1 "fingerprints" the opponent. We maintain a buffer of their last 15 moves and categorize them.

### 6.1 The "George Filter" (Greedy Bot Exploitation)
If the opponent's `PLAIN_MOVE_RATIO` is $> 35\%$, they are classified as a "George"—a bot that lacks deep lookahead and plays greedily.
- **Response**: We immediately slash our `lambda_denial` (stop trying to "hide" information from them) and boost our `alpha` (raw scoring) by $30\%$. 

---

## 7. The Tactician: Carpet Planner (DP)
Alpha-Beta is "Tactically Brilliant but Macroscopically Blind." It cannot easily see that walking 4 steps to a specific corner is the setup for a 12-point carpet. 

The **Carpet Planner** solves this using Dynamic Programming. It scans our Voronoi territory for **Straight Rays** and **Elbow Chains**, calculates the **Points-per-Tempo (PPT)**, and feeds the first move into the search engine as a **Move Hint**. This ensures the bot's deep search always starts by evaluating the most strategically sound macro-play.

---

## 8. Known Limitations & Analysis
1.  **Search Hysteresis**: Identified in v5.1 analysis where the bot would "double-tap" cells it just missed on. Resolved in v5.2 via "Miss Memory."
2.  **Denial Baiting**: Highly deceptive bots can "lure" Yolanda into expensive searches by moving workers close to fake peaks. 

---
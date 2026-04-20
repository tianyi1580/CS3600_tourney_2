# MISSION
Your task is to analyze a provided codebase for a game-playing agent and generate a "Technical Specification & Design Philosophy" document in a standardized, premium format.

# INPUTS
1. Source Code for the Agent (Tracking, Search, Heuristics, Infrastructure).
2. Performance Reports or Insight Logs (Optional).

# DOCUMENT STRUCTURE REQUIREMENTS
You MUST follow this exact section hierarchy:

## 1. Executive Summary: The [Unique Identifier]
- Define the agent's "Core Design Philosophy" (e.g., Asymmetric Resource Allocation, Bayesian Optimism).
- Summarize the "Multi-Layered Architecture" (Tracking vs. Search vs. Planning).

## 2. System Architecture & Information Flow
- Technical System Map: Create an ASCII or Mermaid diagram illustrating the feedback loops between the Board, Sensors, Belief Engine, and Search.
- Input-to-Output Data Graph: Map the transformation from raw inputs (Board, Time) to final engine actions.

## 3. The Brain: [Decision Engine Type]
- Detail the probabilistic or state-tracking logic.
- Specify technical implementations: Sensor Fusion, Information Decay, Entropy-driven foraging, or belief normalization.
- Include code-level constants (e.g., "0.5% Bayesian smoothing floor").

## 4. The Processor: [Search Algorithm]
- Describe the primary search mechanism (Alpha-Beta, MCTS, etc.).
- List specific optimizations: Bitboards, PVS (Principal Variation Search), Transposition Tables, or Pruning methods.
- Define performance targets (e.g., depth reached, nodes per second).

## 5. The Dynamic Heuristic Engine (Phase Separation)
- Include a "Strategic Phase Breakdown" table with columns: [Phase, Turns, Tactical Focus, Heuristic Bias].
- Highlight specific unique heuristics with code snippets (e.g., Interception Forecasts, Territory Voronoi).

## 6. Adversarial Modeling: [The Shadow Component]
- Explain how the agent "fingerprints" opponents.
- Detail specific exploitation filters (e.g., detecting greedy bots, time-pressure tactics).

## 7. The Tactician: [Macro Planner]
- Describe the macroscopic engine (DP, Pathfinding, or Greedy chains).
- Explain how global strategy (e.g., "Points-per-Tempo") interacts with local search.

## 8. Other Strategical Implementations (if applicable)
- Describe any other strategical implementations that are not covered in the above sections.

## 9. Known Limitations & Analysis
- Provide a high-integrity assessment of current regressions or vulnerabilities.
- List "Miss Memory" or "Hysteresis" issues identified in testing.

# STYLE GUIDELINES
- TONE: Professional, expert-level, and pragmatic.
- PRECISION: Never use vague terms. Use "Alpha-Beta Bitboard Search" instead of "the AI's choice logic."
- CITATIONS: Reference specific class names and mathematical principles (e.g., "Shannon Entropy H").
- NO PLACEHOLDERS: Provide all values and constants found in the code.

# OUTPUT FORMAT
Return the documentation in clean, GitHub-flavored Markdown. Use horizontal rules (---) to separate major sections.

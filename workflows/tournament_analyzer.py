#!/usr/bin/env python3
"""
Tournament-Wide Match Intelligence Pipeline
============================================
Scans the full bytefight_cs3600_sp2026 dataset (~121K matches),
fingerprints bots, computes ELO ratings, extracts deep behavioral
profiles for elite bots, and generates actionable intelligence.

Usage:
    python3 workflows/tournament_analyzer.py [--data-dir DIR] [--output-dir DIR]
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "bytefight_cs3600_sp2026"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "tournament"
DEFAULT_ERRLOG_FILE = ROOT / "top_errlog.txt"

# ─── Carpet points table from game rules ───
CARPET_POINTS = {1: -1, 2: 2, 3: 4, 4: 6, 5: 10, 6: 15, 7: 21}

# ─── Bot fingerprinting ───

# Ordered list of (prefix, bot_name) for known bots.
# Order matters: first match wins. Prefixes are checked with startswith().
KNOWN_BOT_RULES: list[tuple[str, str]] = []


def _load_errlog_file(path: Path) -> list[str]:
    """Load errlog prefixes from the user-provided file."""
    if not path.exists():
        return []
    lines = path.read_text().strip().splitlines()
    return [line.strip() for line in lines if line.strip()]


def _build_fingerprint_rules(errlog_prefixes: list[str]) -> None:
    """Build fingerprint rules from user-provided prefixes + hardcoded discovery."""
    global KNOWN_BOT_RULES
    rules: list[tuple[str, str]] = []

    # User-provided prefixes get priority names
    user_names = {
        "Argghhhh": "Argghhhh",
        "Yolanda Prime": "Yolanda_Prime_OURS",
        "Kronos": "Kronos",
        "Search depth history:": "SearchDepthBot",
        "gamma_turbo_": "GammaTurbo",
        "S:": "S_Bot",
        "the game is afoot": "GameIsAfoot",
        "Excalibur ftw": "Excalibur",
    }

    for prefix in errlog_prefixes:
        name = user_names.get(prefix, prefix.replace(" ", "_")[:30])
        rules.append((prefix, name))

    # Additional discovered patterns from fingerprint analysis
    extra_rules = [
        ("Kronos:", "Kronos"),
        ("gamma_turbo_v4c ", "GammaTurbo_v4c"),
        ("gamma_turbo_v3 ", "GammaTurbo_v3"),
        ("gamma_turbo_v2 ", "GammaTurbo_v2"),
        ("gamma_turbo_v4cr1 ", "GammaTurbo_v4cr1"),
        ("gamma_turbo_", "GammaTurbo"),
        ("dhruvandallen | eval=cython", "DhruvAndAllen_Cython"),
        ("dhruvandallen agent", "DhruvAndAllen"),
        ("lol ez", "LolEz"),
        ("I hope this gets us the A", "HopeForA"),
        ("Good game :D", "GoodGameBot"),
        ("I am Agent. My presence guarantees your defeat", "AgentBot"),
        ("gg", "GG_Bot"),
        ("Yolanda v3 | HMM", "Yolanda_v3_HMM"),
        ("Yolanda v9 | HMM", "Yolanda_v9_HMM"),
        ("Yolanda v4 | HMM", "Yolanda_v4_HMM"),
        ("Yolanda v5:", "Yolanda_v5"),
        ("Yolanda v6 |", "Yolanda_v6"),
        ("Yolanda bot logic fully operational", "Yolanda_BotLogic"),
        ("Yolanda bot (Refined Apex)", "Yolanda_RefinedApex"),
        ("YolandaG2V4", "YolandaG2V4"),
        ("Yolanda3.4", "Yolanda3_4"),
        ("Yolanda3.3", "Yolanda3_3"),
        ("yolanda_prime_v4:", "Yolanda_Prime_v4"),
        ("yolanda_prime_v3:", "Yolanda_Prime_v3"),
        ("yolanda_prime_v1_2:", "Yolanda_Prime_v1_2"),
        ("########## YOLANDA DEBUG LOG", "Yolanda_DebugLog"),
        ("=== POST-GAME BOX SCORE ===", "BoxScoreBot"),
        ("NashV3 d=", "NashV3"),
        ("Agent5 checking in with advanced MCTS", "Agent5_MCTS"),
        ("Everything Not Saved Will Be Lost", "EverythingNotSaved"),
        ("Good game!", "GoodGameExcl"),
        ("Good Game!", "GoodGameCapExcl"),
        ("Baseline: HMM belief + iterative-deepening negamax", "BaselineHMM"),
        ("Curious George", "CuriousGeorge"),
        ("I think, therefore I am", "Descartes"),
        ("George is seeking", "George_Seeking"),
        ("George dreams", "George_Dreams"),
        ("George needs", "George_Needs"),
        ("George will remember", "George_Remember"),
        ("George's Institute", "George_Institute"),
        ("MIT: The Georgia Tech", "MIT_GT"),
        ("Maybe George", "George_Maybe"),
        ("If George had a nickel", "George_Nickel"),
        ("Invest in Cloudman Capital", "CloudmanCapital"),
        ("Still better than Siri", "BetterThanSiri"),
        ("Banana Peel was here", "BananaPeel"),
        ("OmegaBot", "OmegaBot"),
        ("All futures computed", "AllFutures"),
        ("THWG!", "THWG"),
        ("i'm tired", "ImTired"),
        ("Answered by Ansel on Edstem", "AnselEdstem"),
        ("Rattus says", "Rattus"),
        ("PaceMax turns=", "PaceMax"),
        ("Garry (Stockfish-style", "Garry_Stockfish"),
        ("ID Alpha-Beta + HMM", "ID_AlphaBeta_HMM"),
        ("Objective-C:", "ObjectiveC"),
        ("jeff", "Jeff"),
        ("Can we fix it???", "CanWeFix"),
        ("James: You can't escape", "James_Saboteur"),
        ("Long Game Agent:", "LongGameAgent"),
        ("RattleBot", "RattleBot"),
        ("score now", "ScoreNow"),
        ("AGI IS ONLY", "AGI_2Years"),
        ("Traceback (most recent call last)", "CRASHED_BOT"),
        ("Timeout", "TIMEOUT_BOT"),
    ]

    for prefix, name in extra_rules:
        # Don't add duplicates
        if not any(p == prefix for p, _ in rules):
            rules.append((prefix, name))

    KNOWN_BOT_RULES = rules


NUMERIC_PATTERN = re.compile(r"^\d+(\.\d+)?$")

# Patterns to consolidate variant bots into single identities
_CONSOLIDATION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^turns=40, nodes=\d+, depth=\d+, root="), "AlphaBetaNodes_Bot"),
    (re.compile(r"^turns=40, searches=\d+, hits=\d+, belief_pea"), "BeliefSearch_Bot"),
    (re.compile(r"^turns=40, searches=\d+, avg_search_p="), "AvgSearchP_Bot"),
    (re.compile(r"^Turns played: 40\. Rat belief peak:"), "RatBeliefPeak_Bot"),
    (re.compile(r"^Turns played: 40\s*$"), "TurnsPlayed40_Bot"),
    (re.compile(r"^Turns played: 40\nTotal time spent:"), "TurnsTimeSpent_Bot"),
    (re.compile(r"^Bot summary:\n\s*searchMoves=\d+"), "BotSummary_Bot"),
    (re.compile(r"^Turns: 40 \| Rat catches:"), "TurnsCatches_Bot"),
    (re.compile(r"^Searched \d+ time\(s\)"), "SearchedTimes_Bot"),
    (re.compile(r"^t=40 s=\d+ h=\d+"), "TurnSearchHits_Bot"),
    (re.compile(r"^GZHAD\d"), "GZHAD_Bot"),
    (re.compile(r"^HybridScout turns="), "HybridScout_Bot"),
    (re.compile(r"^AZAgent \[AZ\+search\]"), "AZAgent_Bot"),
    (re.compile(r"^v\d+ Grandmaster"), "Grandmaster_Bot"),
    (re.compile(r"^CarpetKing v\d+"), "CarpetKing_Bot"),
    (re.compile(r"^PaceMax turns="), "PaceMax_Bot"),
    (re.compile(r"^NashV3 d="), "NashV3_Bot"),
    (re.compile(r"^ID Alpha-Beta \+ HMM"), "ID_AlphaBeta_HMM"),
    (re.compile(r"^Yolanda v3 \|"), "Yolanda_v3_HMM"),
    (re.compile(r"^Yolanda v9 \|"), "Yolanda_v9_HMM"),
    (re.compile(r"^Yolanda v4 \|"), "Yolanda_v4_HMM"),
    (re.compile(r"^Yolanda v5:"), "Yolanda_v5"),
    (re.compile(r"^Yolanda v6 \|"), "Yolanda_v6"),
    (re.compile(r"^Yolanda bot logic fully operational"), "Yolanda_BotLogic"),
    (re.compile(r"^Yolanda bot \(Refined Apex\)"), "Yolanda_RefinedApex"),
    (re.compile(r"^YolandaG2V4"), "YolandaG2V4"),
    (re.compile(r"^Yolanda3\.4"), "Yolanda3_4"),
    (re.compile(r"^Yolanda3\.3"), "Yolanda3_3"),
    (re.compile(r"^yolanda_prime_v4:"), "Yolanda_Prime_v4"),
    (re.compile(r"^yolanda_prime_v3:"), "Yolanda_Prime_v3"),
    (re.compile(r"^yolanda_prime_v1_2:"), "Yolanda_Prime_v1_2"),
    (re.compile(r"^Yolanda \(ExpectiMinimax\+HMM\)"), "Yolanda_Expecti"),
    (re.compile(r"^########## YOLANDA DEBUG LOG"), "Yolanda_DebugLog"),
    (re.compile(r"^Hubert_Skeletrix:"), "Hubert_Skeletrix"),
    (re.compile(r"^Johnson agent:"), "Johnson_Agent"),
    (re.compile(r"^Baseline_v\d+:"), "Baseline_vN"),
    (re.compile(r"^dhruvandallen \| eval=cython"), "DhruvAndAllen_Cython"),
    (re.compile(r"^dhruvandallen agent"), "DhruvAndAllen"),
    (re.compile(r"^\(improved agent\)"), "ImprovedAgent"),
    (re.compile(r"^(Venator Muris|\(Venator)"), "VenatorMuris"),
    (re.compile(r"^searches="), "SearchesEq_Bot"),
    (re.compile(r"^belief_peak="), "BeliefPeak_Bot"),
    (re.compile(r"^RattleBot"), "RattleBot"),
    (re.compile(r"^Long Game Agent:"), "LongGameAgent"),
    (re.compile(r"^=== POST-GAME BOX SCORE ==="), "BoxScore_Bot"),
]


def fingerprint_errlog(errlog: str) -> str:
    """Convert an errlog string to a stable bot identity fingerprint."""
    e = errlog.strip()
    if not e or e == "commentary failed":
        return "UNKNOWN"

    # Check known rules first (user-provided prefixes)
    for prefix, name in KNOWN_BOT_RULES:
        if e.startswith(prefix):
            return name

    # Check consolidation patterns
    for pat, name in _CONSOLIDATION_PATTERNS:
        if pat.search(e):
            return name

    # Pure numeric (like '12.85') — one specific bot outputs just a number
    if NUMERIC_PATTERN.match(e):
        return "NumericBot"

    # JSON blob
    if e.startswith("{"):
        return "JSON_Bot"

    # George variants (many different George quotes)
    if "George" in e:
        return "George_Variant"

    # Crash/error indicators
    if e.startswith("Traceback (most recent call last)"):
        return "CRASHED_BOT"
    if e.startswith("Process killed by SIGKILL"):
        return "SIGKILL_BOT"
    if e == "Timeout":
        return "TIMEOUT_BOT"

    # Fallback: first 40 chars stripped of trailing numbers
    sig = re.sub(r"[\d\.\,]+$", "", e[:40]).strip()
    if len(sig) < 3:
        sig = e[:20]
    return f"UNK:{sig}"


# ─── Match record extraction ───

@dataclass
class MatchRecord:
    """Lightweight per-match record for fast analysis."""
    match_id: str
    result: int             # 0=A wins, 1=B wins, 2=tie
    reason: str
    turn_count: int
    a_final_score: float
    b_final_score: float
    a_time_left: float
    b_time_left: float
    a_bot: str
    b_bot: str
    # Move distributions (counts over game)
    a_prime: int
    a_carpet: int
    a_search: int
    a_plain: int
    b_prime: int
    b_carpet: int
    b_search: int
    b_plain: int
    # Search outcomes
    a_search_catches: int
    b_search_catches: int
    # Score trajectories (sampled)
    a_scores: list[float]
    b_scores: list[float]
    # Time trajectories (sampled)
    a_times: list[float]
    b_times: list[float]
    # Carpet details
    a_carpet_lengths: list[int]
    b_carpet_lengths: list[int]
    # Blocked positions for map fingerprinting
    blocked_count: int


def _count_moves(left_behind: list[str], start: int, step: int) -> tuple[int, int, int, int]:
    """Count move types for a single player from interleaved left_behind."""
    prime = carpet = search = plain = 0
    for i in range(start, len(left_behind), step):
        mode = left_behind[i]
        if mode == "prime":
            prime += 1
        elif mode == "carpet":
            carpet += 1
        elif mode == "search":
            search += 1
        else:
            plain += 1
    return prime, carpet, search, plain


def _count_search_catches(left_behind: list[str], rat_caught: list[bool],
                          start: int, step: int) -> int:
    """Count successful searches for a single player."""
    catches = 0
    for i in range(start, min(len(left_behind), len(rat_caught)), step):
        if left_behind[i] == "search" and rat_caught[i]:
            catches += 1
    return catches


def _extract_carpet_lengths(new_carpets: list[list], start: int, step: int) -> list[int]:
    """Extract carpet roll lengths for a single player."""
    lengths = []
    for i in range(start, len(new_carpets), step):
        carpets = new_carpets[i]
        if isinstance(carpets, list) and carpets:
            lengths.append(len(carpets))
    return lengths


def extract_match(filepath: str) -> MatchRecord | None:
    """Parse a single match JSON into a lightweight MatchRecord."""
    try:
        with open(filepath) as f:
            d = json.load(f)
    except Exception:
        return None

    if not isinstance(d, dict):
        return None

    turn_count = d.get("turn_count")
    if not isinstance(turn_count, int) or turn_count <= 0:
        return None

    result = d.get("result", -1)
    if not isinstance(result, int):
        return None
    reason = str(d.get("reason", "UNKNOWN"))

    # Scores
    a_points = d.get("a_points", [])
    b_points = d.get("b_points", [])
    if not isinstance(a_points, list) or not isinstance(b_points, list):
        return None
    a_final = float(a_points[-1]) if a_points else 0.0
    b_final = float(b_points[-1]) if b_points else 0.0

    # Time
    a_time = d.get("a_time_left", [])
    b_time = d.get("b_time_left", [])
    a_time_left = float(a_time[-1]) if isinstance(a_time, list) and a_time else 0.0
    b_time_left = float(b_time[-1]) if isinstance(b_time, list) and b_time else 0.0

    # Bot identity
    errlog_a = d.get("errlog_a", "")
    errlog_b = d.get("errlog_b", "")
    if not isinstance(errlog_a, str):
        errlog_a = ""
    if not isinstance(errlog_b, str):
        errlog_b = ""
    a_bot = fingerprint_errlog(errlog_a)
    b_bot = fingerprint_errlog(errlog_b)

    # Move distributions
    left_behind = d.get("left_behind", [])
    rat_caught = d.get("rat_caught", [])
    new_carpets = d.get("new_carpets", [])

    if not isinstance(left_behind, list):
        left_behind = []
    if not isinstance(rat_caught, list):
        rat_caught = []
    if not isinstance(new_carpets, list):
        new_carpets = []

    # Turns are interleaved: index 0 is initial state,
    # indices 1,3,5... are player A turns, 2,4,6... are player B turns
    a_prime, a_carpet, a_search, a_plain = _count_moves(left_behind, 1, 2)
    b_prime, b_carpet, b_search, b_plain = _count_moves(left_behind, 2, 2)

    a_catches = _count_search_catches(left_behind, rat_caught, 1, 2)
    b_catches = _count_search_catches(left_behind, rat_caught, 2, 2)

    a_carpet_lengths = _extract_carpet_lengths(new_carpets, 1, 2)
    b_carpet_lengths = _extract_carpet_lengths(new_carpets, 2, 2)

    # Blocked positions
    blocked = d.get("blocked_positions", [])
    blocked_count = len(blocked) if isinstance(blocked, list) else 0

    # Score/time trajectories (keep full for deep analysis)
    a_scores = [float(x) for x in a_points] if isinstance(a_points, list) else []
    b_scores = [float(x) for x in b_points] if isinstance(b_points, list) else []
    a_times_list = [float(x) for x in a_time] if isinstance(a_time, list) else []
    b_times_list = [float(x) for x in b_time] if isinstance(b_time, list) else []

    match_id = Path(filepath).stem
    return MatchRecord(
        match_id=match_id,
        result=result,
        reason=reason,
        turn_count=turn_count,
        a_final_score=a_final,
        b_final_score=b_final,
        a_time_left=a_time_left,
        b_time_left=b_time_left,
        a_bot=a_bot,
        b_bot=b_bot,
        a_prime=a_prime,
        a_carpet=a_carpet,
        a_search=a_search,
        a_plain=a_plain,
        b_prime=b_prime,
        b_carpet=b_carpet,
        b_search=b_search,
        b_plain=b_plain,
        a_search_catches=a_catches,
        b_search_catches=b_catches,
        a_scores=a_scores,
        b_scores=b_scores,
        a_times=a_times_list,
        b_times=b_times_list,
        a_carpet_lengths=a_carpet_lengths,
        b_carpet_lengths=b_carpet_lengths,
        blocked_count=blocked_count,
    )


# ─── Stage 1: Scan all matches ───

def scan_all_matches(data_dir: Path, progress_interval: int = 5000) -> list[MatchRecord]:
    """Scan all match JSONs and extract lightweight records."""
    files = sorted(data_dir.glob("*.json"))
    total = len(files)
    print(f"[Stage 1] Scanning {total} match files...")

    records: list[MatchRecord] = []
    failures = 0
    t0 = time.time()

    for i, filepath in enumerate(files):
        rec = extract_match(str(filepath))
        if rec is not None:
            records.append(rec)
        else:
            failures += 1

        if (i + 1) % progress_interval == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (total - i - 1) / rate
            print(f"  [{i+1}/{total}] {len(records)} parsed, {failures} failed "
                  f"({elapsed:.1f}s elapsed, ETA {eta:.0f}s)")

    elapsed = time.time() - t0
    print(f"  Done: {len(records)} records from {total} files in {elapsed:.1f}s "
          f"({failures} failures, {failures/total*100:.1f}%)")
    return records


# ─── Stage 2: Bot roster & ELO ───

@dataclass
class BotProfile:
    """Accumulated statistics for a single bot identity."""
    name: str
    match_count: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0
    total_score: float = 0.0
    total_opp_score: float = 0.0
    total_time_left: float = 0.0
    # Move counts
    total_prime: int = 0
    total_carpet: int = 0
    total_search: int = 0
    total_plain: int = 0
    total_search_catches: int = 0
    total_turns: int = 0
    # Carpet details
    carpet_lengths: list[int] = field(default_factory=list)
    # Score deltas
    score_deltas: list[float] = field(default_factory=list)
    # Time left at end
    time_lefts: list[float] = field(default_factory=list)
    # Per-phase move distributions (early/mid/late each 1/3 of 40 turns)
    phase_search: dict[str, int] = field(default_factory=lambda: {"early": 0, "mid": 0, "late": 0})
    phase_prime: dict[str, int] = field(default_factory=lambda: {"early": 0, "mid": 0, "late": 0})
    phase_carpet: dict[str, int] = field(default_factory=lambda: {"early": 0, "mid": 0, "late": 0})
    phase_plain: dict[str, int] = field(default_factory=lambda: {"early": 0, "mid": 0, "late": 0})
    phase_turns: dict[str, int] = field(default_factory=lambda: {"early": 0, "mid": 0, "late": 0})
    # ELO (set later)
    elo: float = 1500.0
    # Opponents beaten / lost to
    opponents: dict[str, dict[str, int]] = field(default_factory=dict)


def _phase_for_player_turn(player_turn: int) -> str:
    """Map a per-player turn number (0-39) to phase."""
    if player_turn < 14:
        return "early"
    elif player_turn < 27:
        return "mid"
    else:
        return "late"


def build_bot_profiles(records: list[MatchRecord]) -> dict[str, BotProfile]:
    """Build per-bot aggregate profiles from all match records."""
    profiles: dict[str, BotProfile] = {}

    def ensure(name: str) -> BotProfile:
        if name not in profiles:
            profiles[name] = BotProfile(name=name)
        return profiles[name]

    for rec in records:
        if rec.reason not in ("POINTS",):
            # Include crash/timeout matches but only count them if the bot didn't crash
            pass

        # Process both sides
        for side in ("a", "b"):
            bot = rec.a_bot if side == "a" else rec.b_bot
            opp = rec.b_bot if side == "a" else rec.a_bot
            prof = ensure(bot)
            prof.match_count += 1

            # Determine win/loss from this bot's perspective
            # result=0 means A wins, result=1 means B wins, result=2 means tie
            if rec.result == 2:
                prof.ties += 1
            elif (rec.result == 0 and side == "a") or (rec.result == 1 and side == "b"):
                prof.wins += 1
            else:
                prof.losses += 1

            my_score = rec.a_final_score if side == "a" else rec.b_final_score
            opp_score = rec.b_final_score if side == "a" else rec.a_final_score
            prof.total_score += my_score
            prof.total_opp_score += opp_score
            prof.score_deltas.append(my_score - opp_score)

            time_left = rec.a_time_left if side == "a" else rec.b_time_left
            prof.total_time_left += time_left
            prof.time_lefts.append(time_left)

            prime = rec.a_prime if side == "a" else rec.b_prime
            carpet = rec.a_carpet if side == "a" else rec.b_carpet
            search = rec.a_search if side == "a" else rec.b_search
            plain = rec.a_plain if side == "a" else rec.b_plain
            catches = rec.a_search_catches if side == "a" else rec.b_search_catches
            c_lengths = rec.a_carpet_lengths if side == "a" else rec.b_carpet_lengths

            prof.total_prime += prime
            prof.total_carpet += carpet
            prof.total_search += search
            prof.total_plain += plain
            prof.total_search_catches += catches
            prof.total_turns += prime + carpet + search + plain
            prof.carpet_lengths.extend(c_lengths)

            # Track opponent matchups
            if opp not in prof.opponents:
                prof.opponents[opp] = {"wins": 0, "losses": 0, "ties": 0}
            if rec.result == 2:
                prof.opponents[opp]["ties"] += 1
            elif (rec.result == 0 and side == "a") or (rec.result == 1 and side == "b"):
                prof.opponents[opp]["wins"] += 1
            else:
                prof.opponents[opp]["losses"] += 1

    return profiles


def compute_elo(profiles: dict[str, BotProfile], records: list[MatchRecord],
                k: float = 32.0, iterations: int = 20) -> None:
    """Iterative ELO computation from pairwise results.
    
    CRITICAL: Only count POINTS-decided matches to avoid inflating ELO
    for bots whose opponents crash/timeout.
    """
    # Collect pairwise results from POINTS matches only
    pairwise: dict[tuple[str, str], dict[str, int]] = {}
    
    for rec in records:
        # ONLY count legitimately decided matches
        if rec.reason != "POINTS":
            continue
        if rec.turn_count < 70:  # Skip truncated matches
            continue
        
        a_bot = rec.a_bot
        b_bot = rec.b_bot
        # Skip unknowns and crash bots
        if a_bot in ("UNKNOWN", "CRASHED_BOT", "TIMEOUT_BOT", "SIGKILL_BOT"):
            continue
        if b_bot in ("UNKNOWN", "CRASHED_BOT", "TIMEOUT_BOT", "SIGKILL_BOT"):
            continue
        
        key = tuple(sorted([a_bot, b_bot]))
        if key not in pairwise:
            pairwise[key] = {"a_wins": 0, "b_wins": 0, "ties": 0}
        
        if rec.result == 2:
            if key[0] == a_bot:
                pairwise[key]["ties"] += 1
            else:
                pairwise[key]["ties"] += 1
        elif rec.result == 0:  # A wins (result=0 means A scored higher)
            if key[0] == a_bot:
                pairwise[key]["a_wins"] += 1
            else:
                pairwise[key]["b_wins"] += 1
        else:  # result=1 means B wins
            if key[0] == b_bot:
                pairwise[key]["a_wins"] += 1
            else:
                pairwise[key]["b_wins"] += 1

    # Iterative ELO updates
    for _ in range(iterations):
        for (a, b), results in pairwise.items():
            if a not in profiles or b not in profiles:
                continue
            ea = 1.0 / (1.0 + 10 ** ((profiles[b].elo - profiles[a].elo) / 400.0))
            total = results["a_wins"] + results["b_wins"] + results["ties"]
            if total == 0:
                continue
            sa = (results["a_wins"] + 0.5 * results["ties"]) / total
            delta = k * (sa - ea) * math.log2(max(total, 2))
            profiles[a].elo += delta
            profiles[b].elo -= delta


# ─── Stage 3: Deep behavioral analysis ───

@dataclass
class EliteProfile:
    """Deep behavioral profile for a top-tier bot."""
    name: str
    elo: float
    match_count: int
    win_rate: float
    avg_score: float
    avg_opp_score: float
    avg_score_delta: float
    median_score_delta: float

    # Move allocation (fractions)
    prime_rate: float
    carpet_rate: float
    search_rate: float
    plain_rate: float

    # Search discipline
    search_per_game: float
    search_conversion: float  # catches / searches

    # Carpet efficiency
    avg_carpet_length: float
    carpet_per_game: float
    carpet_points_per_carpet: float  # estimated from avg length

    # Time management
    avg_time_left: float
    median_time_left: float
    time_pressure_rate: float  # fraction of games ending < 10s

    # Phase profiles (early/mid/late move distributions)
    phase_profiles: dict[str, dict[str, float]]

    # Scoring trajectory shape
    avg_score_at_turn: list[float]  # 40-element for each player turn

    # Vulnerability analysis
    loss_rate_by_phase: dict[str, float]  # which phase do they collapse in?
    worst_opponents: list[tuple[str, float, int]]  # (opp, loss_rate, n)
    best_opponents: list[tuple[str, float, int]]


def build_elite_profiles(
    profiles: dict[str, BotProfile],
    records: list[MatchRecord],
    top_n: int = 15,
    min_matches: int = 30,
    min_unique_opps: int = 5,
) -> list[EliteProfile]:
    """Build deep profiles for the top-N bots by ELO."""
    # Filter bots with enough matches AND enough unique opponents
    eligible = {
        name: p for name, p in profiles.items()
        if p.match_count >= min_matches
        and name not in ("UNKNOWN", "CRASHED_BOT", "TIMEOUT_BOT", "SIGKILL_BOT")
        and not name.startswith("UNK:Traceback")
        and not name.startswith("UNK:Process killed")
        and len(p.opponents) >= min_unique_opps
    }

    ranked = sorted(eligible.values(), key=lambda p: p.elo, reverse=True)[:top_n]
    elite_names = {p.name for p in ranked}

    # Build per-bot match lists for trajectory analysis
    bot_matches: dict[str, list[tuple[MatchRecord, str]]] = {n: [] for n in elite_names}
    for rec in records:
        if rec.a_bot in elite_names:
            bot_matches[rec.a_bot].append((rec, "a"))
        if rec.b_bot in elite_names:
            bot_matches[rec.b_bot].append((rec, "b"))

    elite_profiles: list[EliteProfile] = []

    for prof in ranked:
        name = prof.name
        n = prof.match_count
        total_turns = prof.total_turns or 1

        win_rate = (prof.wins + 0.5 * prof.ties) / n if n else 0.0
        avg_score = prof.total_score / n if n else 0.0
        avg_opp = prof.total_opp_score / n if n else 0.0
        avg_delta = statistics.fmean(prof.score_deltas) if prof.score_deltas else 0.0
        med_delta = statistics.median(prof.score_deltas) if prof.score_deltas else 0.0

        prime_rate = prof.total_prime / total_turns
        carpet_rate = prof.total_carpet / total_turns
        search_rate = prof.total_search / total_turns
        plain_rate = prof.total_plain / total_turns

        search_per_game = prof.total_search / n if n else 0.0
        search_conv = prof.total_search_catches / prof.total_search if prof.total_search else 0.0

        avg_cl = statistics.fmean(prof.carpet_lengths) if prof.carpet_lengths else 0.0
        carpet_per_game = prof.total_carpet / n if n else 0.0
        # Estimate carpet points from average length
        carpet_pts = CARPET_POINTS.get(round(avg_cl), 0) if avg_cl > 0 else 0

        avg_time = statistics.fmean(prof.time_lefts) if prof.time_lefts else 0.0
        med_time = statistics.median(prof.time_lefts) if prof.time_lefts else 0.0
        time_pressure = sum(1 for t in prof.time_lefts if t < 10.0) / n if n else 0.0

        # Phase profiles from accumulated records
        # We need to rebuild phase data from match records
        phase_search_counts = {"early": 0, "mid": 0, "late": 0}
        phase_prime_counts = {"early": 0, "mid": 0, "late": 0}
        phase_carpet_counts = {"early": 0, "mid": 0, "late": 0}
        phase_plain_counts = {"early": 0, "mid": 0, "late": 0}
        phase_total = {"early": 0, "mid": 0, "late": 0}

        # Score trajectory (averaged over all games, normalized to 40 player turns)
        score_accum = [0.0] * 40
        score_counts = [0] * 40

        # Loss phase analysis
        loss_phase_deltas = {"early": [], "mid": [], "late": []}

        for rec, side in bot_matches.get(name, []):
            left_behind = []
            # We need to re-extract per-turn data from match
            # Reconstruct from the record's scores
            my_scores = rec.a_scores if side == "a" else rec.b_scores
            opp_scores = rec.b_scores if side == "a" else rec.a_scores

            # Extract player turns from interleaved left_behind
            # We don't have left_behind in the record, so use score trajectory
            start = 1 if side == "a" else 2
            for player_turn in range(40):
                global_turn = start + player_turn * 2
                if global_turn < len(my_scores):
                    score_accum[player_turn] += my_scores[global_turn]
                    score_counts[player_turn] += 1

        avg_score_at_turn = [
            score_accum[i] / score_counts[i] if score_counts[i] > 0 else 0.0
            for i in range(40)
        ]

        # Worst/best opponents
        opp_records: list[tuple[str, float, int]] = []
        for opp, res in prof.opponents.items():
            total_games = res["wins"] + res["losses"] + res["ties"]
            if total_games < 3:
                continue
            lr = res["losses"] / total_games
            opp_records.append((opp, lr, total_games))

        worst = sorted(opp_records, key=lambda x: -x[1])[:5]
        best = sorted(opp_records, key=lambda x: x[1])[:5]

        ep = EliteProfile(
            name=name,
            elo=prof.elo,
            match_count=n,
            win_rate=win_rate,
            avg_score=avg_score,
            avg_opp_score=avg_opp,
            avg_score_delta=avg_delta,
            median_score_delta=med_delta,
            prime_rate=prime_rate,
            carpet_rate=carpet_rate,
            search_rate=search_rate,
            plain_rate=plain_rate,
            search_per_game=search_per_game,
            search_conversion=search_conv,
            avg_carpet_length=avg_cl,
            carpet_per_game=carpet_per_game,
            carpet_points_per_carpet=carpet_pts,
            avg_time_left=avg_time,
            median_time_left=med_time,
            time_pressure_rate=time_pressure,
            phase_profiles={},  # simplified
            avg_score_at_turn=avg_score_at_turn,
            loss_rate_by_phase={},
            worst_opponents=worst,
            best_opponents=best,
        )
        elite_profiles.append(ep)

    return elite_profiles


# ─── Stage 4: Counter-strategy mining ───

def mine_counter_strategies(
    profiles: dict[str, BotProfile],
    elite_profiles: list[EliteProfile],
    records: list[MatchRecord],
    min_matches: int = 5,
) -> dict[str, Any]:
    """For each elite bot, find what strategies beat them."""
    results: dict[str, Any] = {}

    for ep in elite_profiles:
        name = ep.name
        prof = profiles.get(name)
        if not prof:
            continue

        # Find bots that have positive win rate against this elite
        counters: list[dict[str, Any]] = []
        for opp, res in prof.opponents.items():
            total = res["wins"] + res["losses"] + res["ties"]
            if total < min_matches:
                continue
            elite_loss_rate = res["losses"] / total
            if elite_loss_rate > 0.55:  # Opponents that beat this elite > 55%
                opp_prof = profiles.get(opp)
                if not opp_prof or opp_prof.match_count < 10:
                    continue
                opp_total_turns = opp_prof.total_turns or 1
                counters.append({
                    "opponent": opp,
                    "games": total,
                    "elite_loss_rate": elite_loss_rate,
                    "opp_elo": opp_prof.elo,
                    "opp_search_rate": opp_prof.total_search / opp_total_turns,
                    "opp_prime_rate": opp_prof.total_prime / opp_total_turns,
                    "opp_carpet_rate": opp_prof.total_carpet / opp_total_turns,
                    "opp_search_conv": (opp_prof.total_search_catches / opp_prof.total_search
                                       if opp_prof.total_search else 0.0),
                    "opp_avg_carpet_len": (statistics.fmean(opp_prof.carpet_lengths)
                                          if opp_prof.carpet_lengths else 0.0),
                })

        counters.sort(key=lambda x: -x["elite_loss_rate"])

        # Analyze what the elite bot's losses look like
        # result=0 means A wins, result=1 means B wins
        loss_records = []
        for rec in records:
            if rec.a_bot == name and rec.result == 1:  # A lost (B won)
                loss_records.append((rec, "a"))
            elif rec.b_bot == name and rec.result == 0:  # B lost (A won)
                loss_records.append((rec, "b"))

        # Score trajectory in losses vs wins
        loss_deltas = []
        for rec, side in loss_records:
            my_score = rec.a_final_score if side == "a" else rec.b_final_score
            opp_score = rec.b_final_score if side == "a" else rec.a_final_score
            loss_deltas.append(my_score - opp_score)

        results[name] = {
            "counter_bots": counters[:10],
            "loss_count": len(loss_records),
            "avg_loss_delta": statistics.fmean(loss_deltas) if loss_deltas else 0.0,
            "median_loss_delta": statistics.median(loss_deltas) if loss_deltas else 0.0,
        }

    return results


# ─── Stage 5: Report generation ───

def generate_report(
    profiles: dict[str, BotProfile],
    elite_profiles: list[EliteProfile],
    counter_strategies: dict[str, Any],
    records: list[MatchRecord],
    our_bot_names: list[str],
) -> str:
    """Generate the final markdown intelligence report."""
    lines: list[str] = []

    # Find our bot profiles
    our_profiles = [ep for ep in elite_profiles if ep.name in our_bot_names]
    our_in_roster = {name: profiles[name] for name in our_bot_names if name in profiles}

    lines.append("# 🏆 Tournament Intelligence Report")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- **Total matches analyzed**: {len(records):,}")
    lines.append(f"- **Unique bot identities**: {len(profiles):,}")
    eligible = sum(1 for p in profiles.values() if p.match_count >= 30)
    lines.append(f"- **Bots with ≥30 matches**: {eligible}")
    lines.append(f"- **Elite bots profiled**: {len(elite_profiles)}")
    lines.append("")

    # ─── Our bot summary ───
    if our_in_roster:
        lines.append("## 🎯 Our Bot Performance")
        lines.append("")
        for name, prof in our_in_roster.items():
            n = prof.match_count
            wr = (prof.wins + 0.5 * prof.ties) / n if n else 0.0
            total_t = prof.total_turns or 1
            lines.append(f"### {name}")
            lines.append(f"- **ELO**: {prof.elo:.0f}")
            lines.append(f"- **Matches**: {n} (W:{prof.wins} L:{prof.losses} T:{prof.ties})")
            lines.append(f"- **Win Rate**: {wr:.3f}")
            lines.append(f"- **Avg Score Delta**: {statistics.fmean(prof.score_deltas):+.2f}" if prof.score_deltas else "")
            lines.append(f"- **Search Rate**: {prof.total_search/total_t:.3f}")
            lines.append(f"- **Search Conversion**: {prof.total_search_catches/prof.total_search:.3f}" if prof.total_search else "- **Search Conversion**: N/A")
            lines.append(f"- **Prime Rate**: {prof.total_prime/total_t:.3f}")
            lines.append(f"- **Carpet Rate**: {prof.total_carpet/total_t:.3f}")
            lines.append(f"- **Avg Carpet Length**: {statistics.fmean(prof.carpet_lengths):.2f}" if prof.carpet_lengths else "")
            lines.append(f"- **Avg Time Left**: {statistics.fmean(prof.time_lefts):.1f}s" if prof.time_lefts else "")
            lines.append("")

    # ─── ELO Rankings ───
    lines.append("## 📊 ELO Rankings (Top 30)")
    lines.append("")
    lines.append("| Rank | Bot | ELO | Matches | Opps | Win Rate | Avg Δ | Search Rate | Search Conv | Carpet Rate | Avg CL | Time Left |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")

    ranked = sorted(
        [(n, p) for n, p in profiles.items()
         if p.match_count >= 30
         and n not in ("UNKNOWN", "CRASHED_BOT", "TIMEOUT_BOT", "SIGKILL_BOT")
         and not n.startswith("UNK:Traceback")
         and not n.startswith("UNK:Process killed")
         and len(p.opponents) >= 5],
        key=lambda x: -x[1].elo
    )

    for rank, (name, prof) in enumerate(ranked[:30], 1):
        n = prof.match_count
        wr = (prof.wins + 0.5 * prof.ties) / n
        tt = prof.total_turns or 1
        avg_d = statistics.fmean(prof.score_deltas) if prof.score_deltas else 0.0
        sr = prof.total_search / tt
        sc = prof.total_search_catches / prof.total_search if prof.total_search else 0.0
        cr = prof.total_carpet / tt
        acl = statistics.fmean(prof.carpet_lengths) if prof.carpet_lengths else 0.0
        tl = statistics.fmean(prof.time_lefts) if prof.time_lefts else 0.0
        marker = " ⭐" if name in our_bot_names else ""
        n_opps = len(prof.opponents)
        lines.append(
            f"| {rank} | {name}{marker} | {prof.elo:.0f} | {n} | {n_opps} | {wr:.3f} | "
            f"{avg_d:+.1f} | {sr:.3f} | {sc:.3f} | {cr:.3f} | {acl:.1f} | {tl:.0f}s |"
        )

    lines.append("")

    # ─── Elite Bot Deep Profiles ───
    lines.append("## 🔬 Elite Bot Deep Profiles")
    lines.append("")

    for ep in elite_profiles[:10]:
        marker = " ⭐ (OURS)" if ep.name in our_bot_names else ""
        lines.append(f"### {ep.name}{marker}")
        lines.append("")
        lines.append(f"**ELO {ep.elo:.0f} | {ep.match_count} matches | WR {ep.win_rate:.3f} | Avg Δ {ep.avg_score_delta:+.2f}**")
        lines.append("")

        lines.append("| Metric | Value |")
        lines.append("|---|---:|")
        lines.append(f"| Avg Score | {ep.avg_score:.1f} |")
        lines.append(f"| Avg Opp Score | {ep.avg_opp_score:.1f} |")
        lines.append(f"| Prime Rate | {ep.prime_rate:.3f} |")
        lines.append(f"| Carpet Rate | {ep.carpet_rate:.3f} |")
        lines.append(f"| Search Rate | {ep.search_rate:.3f} |")
        lines.append(f"| Plain Rate | {ep.plain_rate:.3f} |")
        lines.append(f"| Searches/Game | {ep.search_per_game:.1f} |")
        lines.append(f"| Search Conversion | {ep.search_conversion:.3f} |")
        lines.append(f"| Avg Carpet Length | {ep.avg_carpet_length:.1f} |")
        lines.append(f"| Carpets/Game | {ep.carpet_per_game:.1f} |")
        lines.append(f"| Avg Time Left | {ep.avg_time_left:.0f}s |")
        lines.append(f"| Time Pressure Rate (<10s) | {ep.time_pressure_rate:.3f} |")
        lines.append("")

        if ep.worst_opponents:
            lines.append("**Worst matchups** (highest loss rate against):")
            for opp, lr, n in ep.worst_opponents[:3]:
                lines.append(f"- vs `{opp}`: {lr:.3f} loss rate ({n} games)")
            lines.append("")

        cs = counter_strategies.get(ep.name, {})
        if cs.get("counter_bots"):
            lines.append("**Counter strategies** (bots that beat this elite >55%):")
            for cb in cs["counter_bots"][:3]:
                lines.append(
                    f"- `{cb['opponent']}` (ELO {cb['opp_elo']:.0f}): "
                    f"beats {cb['elite_loss_rate']:.1%} of the time, "
                    f"SR={cb['opp_search_rate']:.3f}, "
                    f"SC={cb['opp_search_conv']:.3f}, "
                    f"CL={cb['opp_avg_carpet_len']:.1f}"
                )
            lines.append("")

        lines.append("---")
        lines.append("")

    # ─── Meta-Game Insights ───
    lines.append("## 🧠 Meta-Game Insights")
    lines.append("")

    # Compute averages across top-10 elites
    if elite_profiles:
        top = elite_profiles[:10]
        lines.append("### What the Best Bots Do")
        lines.append("")
        lines.append("Averaged across the top-10 ELO bots:")
        lines.append("")

        avg_sr = statistics.fmean([ep.search_rate for ep in top])
        avg_sc = statistics.fmean([ep.search_conversion for ep in top])
        avg_pr = statistics.fmean([ep.prime_rate for ep in top])
        avg_cr = statistics.fmean([ep.carpet_rate for ep in top])
        avg_pl = statistics.fmean([ep.plain_rate for ep in top])
        avg_spg = statistics.fmean([ep.search_per_game for ep in top])
        avg_cpg = statistics.fmean([ep.carpet_per_game for ep in top])
        avg_cl = statistics.fmean([ep.avg_carpet_length for ep in top])
        avg_tl = statistics.fmean([ep.avg_time_left for ep in top])
        avg_wr = statistics.fmean([ep.win_rate for ep in top])
        avg_delta = statistics.fmean([ep.avg_score_delta for ep in top])

        lines.append("| Metric | Top-10 Average | Interpretation |")
        lines.append("|---|---:|---|")
        lines.append(f"| Search Rate | {avg_sr:.3f} | {avg_spg:.1f} searches/game |")
        lines.append(f"| Search Conversion | {avg_sc:.3f} | Target >0.35 for positive EV |")
        lines.append(f"| Prime Rate | {avg_pr:.3f} | Building board position |")
        lines.append(f"| Carpet Rate | {avg_cr:.3f} | {avg_cpg:.1f} carpets/game |")
        lines.append(f"| Plain Rate | {avg_pl:.3f} | Repositioning budget |")
        lines.append(f"| Avg Carpet Length | {avg_cl:.1f} | Target ≥3 for positive points |")
        lines.append(f"| Avg Time Left | {avg_tl:.0f}s | Budget management |")
        lines.append(f"| Win Rate | {avg_wr:.3f} | Against full field |")
        lines.append(f"| Avg Score Delta | {avg_delta:+.1f} | Points margin |")
        lines.append("")

        # Correlations: what separates the top-5 from 6-10
        if len(top) >= 10:
            t5 = top[:5]
            b5 = top[5:10]
            lines.append("### What Separates Rank 1-5 from 6-10")
            lines.append("")
            lines.append("| Metric | Rank 1-5 | Rank 6-10 | Gap |")
            lines.append("|---|---:|---:|---:|")
            for metric, getter in [
                ("Search Rate", lambda ep: ep.search_rate),
                ("Search Conv", lambda ep: ep.search_conversion),
                ("Prime Rate", lambda ep: ep.prime_rate),
                ("Carpet Rate", lambda ep: ep.carpet_rate),
                ("Avg Carpet Len", lambda ep: ep.avg_carpet_length),
                ("Carpets/Game", lambda ep: ep.carpet_per_game),
                ("Avg Time Left", lambda ep: ep.avg_time_left),
                ("Win Rate", lambda ep: ep.win_rate),
            ]:
                v5 = statistics.fmean([getter(ep) for ep in t5])
                v10 = statistics.fmean([getter(ep) for ep in b5])
                gap = v5 - v10
                lines.append(f"| {metric} | {v5:.3f} | {v10:.3f} | {gap:+.3f} |")
            lines.append("")

    # ─── Actionable Recommendations for Yolanda ───
    lines.append("## 🎯 Actionable Recommendations for Yolanda Prime")
    lines.append("")

    if elite_profiles:
        top1 = elite_profiles[0]
        top3_avg = lambda getter: statistics.fmean([getter(ep) for ep in elite_profiles[:3]])

        lines.append("### Concrete Parameter Targets")
        lines.append("")
        lines.append("Based on empirical data from the tournament's strongest performers:")
        lines.append("")
        lines.append(f"1. **Search Rate Target**: {top3_avg(lambda ep: ep.search_rate):.3f} "
                     f"({top3_avg(lambda ep: ep.search_per_game):.1f} searches/game)")
        lines.append(f"2. **Search Conversion Floor**: {top3_avg(lambda ep: ep.search_conversion):.3f} "
                     f"(below this, reduce search frequency)")
        lines.append(f"3. **Carpet Length Target**: ≥{top3_avg(lambda ep: ep.avg_carpet_length):.1f} "
                     f"(aim for rolls of 3+ for positive EV)")
        lines.append(f"4. **Prime Rate**: {top3_avg(lambda ep: ep.prime_rate):.3f} "
                     f"(invest in board building)")
        lines.append(f"5. **Time Budget**: Keep ≥{top3_avg(lambda ep: ep.avg_time_left):.0f}s at game end "
                     f"(time pressure rate should be <{top3_avg(lambda ep: ep.time_pressure_rate):.2f})")
        lines.append(f"6. **Target Score**: {top3_avg(lambda ep: ep.avg_score):.1f} points/game "
                     f"(vs opponent avg {top3_avg(lambda ep: ep.avg_opp_score):.1f})")
        lines.append("")

        # Compare our bot to the meta if available
        if our_profiles:
            lines.append("### Gap Analysis: Our Bot vs Top-3 Average")
            lines.append("")
            our = our_profiles[0]
            lines.append("| Metric | Our Bot | Top-3 Avg | Gap | Action |")
            lines.append("|---|---:|---:|---:|---|")

            t3sr = top3_avg(lambda ep: ep.search_rate)
            t3sc = top3_avg(lambda ep: ep.search_conversion)
            t3pr = top3_avg(lambda ep: ep.prime_rate)
            t3cr = top3_avg(lambda ep: ep.carpet_rate)
            t3cl = top3_avg(lambda ep: ep.avg_carpet_length)
            t3tl = top3_avg(lambda ep: ep.avg_time_left)

            def action(ours_v: float, target: float, metric: str) -> str:
                gap = ours_v - target
                if abs(gap) < 0.01:
                    return "✅ On target"
                elif gap > 0:
                    return f"⬇️ Reduce by {gap:.3f}"
                else:
                    return f"⬆️ Increase by {abs(gap):.3f}"

            lines.append(f"| Search Rate | {our.search_rate:.3f} | {t3sr:.3f} | {our.search_rate-t3sr:+.3f} | {action(our.search_rate, t3sr, 'search')} |")
            lines.append(f"| Search Conv | {our.search_conversion:.3f} | {t3sc:.3f} | {our.search_conversion-t3sc:+.3f} | {action(our.search_conversion, t3sc, 'search_conv')} |")
            lines.append(f"| Prime Rate | {our.prime_rate:.3f} | {t3pr:.3f} | {our.prime_rate-t3pr:+.3f} | {action(our.prime_rate, t3pr, 'prime')} |")
            lines.append(f"| Carpet Rate | {our.carpet_rate:.3f} | {t3cr:.3f} | {our.carpet_rate-t3cr:+.3f} | {action(our.carpet_rate, t3cr, 'carpet')} |")
            lines.append(f"| Avg Carpet Len | {our.avg_carpet_length:.1f} | {t3cl:.1f} | {our.avg_carpet_length-t3cl:+.1f} | {action(our.avg_carpet_length, t3cl, 'cl')} |")
            lines.append(f"| Avg Time Left | {our.avg_time_left:.0f}s | {t3tl:.0f}s | {our.avg_time_left-t3tl:+.0f}s | {action(our.avg_time_left, t3tl, 'time')} |")
            lines.append("")

    # ─── Score distribution ───
    lines.append("## 📈 Tournament Score Distribution")
    lines.append("")
    all_scores_a = [r.a_final_score for r in records if r.turn_count == 80]
    all_scores_b = [r.b_final_score for r in records if r.turn_count == 80]
    all_scores = all_scores_a + all_scores_b
    if all_scores:
        lines.append(f"- **Mean final score**: {statistics.fmean(all_scores):.1f}")
        lines.append(f"- **Median final score**: {statistics.median(all_scores):.1f}")
        lines.append(f"- **Std dev**: {statistics.stdev(all_scores):.1f}")
        lines.append(f"- **P90 score**: {sorted(all_scores)[int(0.9*len(all_scores))]:.1f}")
        lines.append(f"- **P95 score**: {sorted(all_scores)[int(0.95*len(all_scores))]:.1f}")
        lines.append(f"- **Max score**: {max(all_scores):.1f}")
        lines.append("")

    # ─── Archetype distribution ───
    lines.append("## 🏷️ Bot Archetype Distribution")
    lines.append("")
    archetype_counts = collections.Counter()
    for name, prof in profiles.items():
        if prof.match_count < 10:
            continue
        tt = prof.total_turns or 1
        sr = prof.total_search / tt
        pr = prof.total_prime / tt
        cr = prof.total_carpet / tt
        if sr > 0.25:
            archetype_counts["Search-Heavy"] += 1
        elif pr > 0.45:
            archetype_counts["Prime-Heavy"] += 1
        elif cr > 0.15:
            archetype_counts["Carpet-Focused"] += 1
        else:
            archetype_counts["Balanced"] += 1

    for arch, count in archetype_counts.most_common():
        lines.append(f"- **{arch}**: {count} bots")
    lines.append("")

    return "\n".join(lines) + "\n"


# ─── Main pipeline ───

def main() -> int:
    parser = argparse.ArgumentParser(description="Tournament-wide match intelligence pipeline")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                        help="Directory containing match JSON files")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="Output directory for reports")
    parser.add_argument("--errlog-file", type=Path, default=DEFAULT_ERRLOG_FILE,
                        help="File with known bot errlog prefixes")
    parser.add_argument("--top-n", type=int, default=15,
                        help="Number of elite bots to profile deeply")
    parser.add_argument("--min-matches", type=int, default=30,
                        help="Minimum matches for a bot to be ranked")
    args = parser.parse_args()

    t_start = time.time()

    # Load errlog prefixes and build fingerprint rules
    errlog_prefixes = _load_errlog_file(args.errlog_file)
    _build_fingerprint_rules(errlog_prefixes)
    print(f"Loaded {len(errlog_prefixes)} errlog prefixes, "
          f"{len(KNOWN_BOT_RULES)} fingerprint rules")

    # Stage 1: Scan
    records = scan_all_matches(args.data_dir)
    if not records:
        print("ERROR: No records extracted!")
        return 1

    # Stage 2: Build profiles & ELO
    print(f"\n[Stage 2] Building bot profiles and ELO ratings...")
    t2 = time.time()
    profiles = build_bot_profiles(records)
    compute_elo(profiles, records, iterations=30)
    print(f"  {len(profiles)} bot identities found in {time.time()-t2:.1f}s")

    # Print quick roster summary
    ranked = sorted(
        [(n, p) for n, p in profiles.items()
         if p.match_count >= args.min_matches
         and n not in ("UNKNOWN", "CRASHED_BOT", "TIMEOUT_BOT", "SIGKILL_BOT")
         and not n.startswith("UNK:Traceback")
         and not n.startswith("UNK:Process killed")
         and len(p.opponents) >= 5],  # Must have played at least 5 unique opponents
        key=lambda x: -x[1].elo
    )
    print(f"  {len(ranked)} bots with ≥{args.min_matches} matches")
    print(f"  Top 5: {', '.join(f'{n}({p.elo:.0f})' for n, p in ranked[:5])}")

    # Identify our bots
    our_bot_names = []
    for n, p in profiles.items():
        if n.startswith("Yolanda_Prime"):
            our_bot_names.append(n)
    if our_bot_names:
        print(f"  Our bots found: {', '.join(our_bot_names)}")

    # Stage 3: Elite profiles
    print(f"\n[Stage 3] Building elite bot profiles...")
    t3 = time.time()
    elite_profiles = build_elite_profiles(profiles, records, top_n=args.top_n,
                                          min_matches=args.min_matches,
                                          min_unique_opps=5)
    print(f"  {len(elite_profiles)} elite profiles in {time.time()-t3:.1f}s")

    # Stage 4: Counter strategies
    print(f"\n[Stage 4] Mining counter-strategies...")
    t4 = time.time()
    counter_strategies = mine_counter_strategies(profiles, elite_profiles, records)
    print(f"  Done in {time.time()-t4:.1f}s")

    # Stage 5: Report generation
    print(f"\n[Stage 5] Generating reports...")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Generate markdown report
    report = generate_report(profiles, elite_profiles, counter_strategies,
                            records, our_bot_names)
    report_path = args.output_dir / "tournament_intelligence.md"
    report_path.write_text(report)
    print(f"  Report: {report_path}")

    # Save ELO rankings CSV
    elo_path = args.output_dir / "elo_rankings.csv"
    with open(elo_path, "w") as f:
        f.write("rank,bot,elo,matches,wins,losses,ties,win_rate,avg_score_delta,"
                "search_rate,search_conversion,prime_rate,carpet_rate,avg_carpet_len,"
                "avg_time_left\n")
        for rank, (name, prof) in enumerate(ranked, 1):
            n = prof.match_count
            wr = (prof.wins + 0.5 * prof.ties) / n
            tt = prof.total_turns or 1
            avg_d = statistics.fmean(prof.score_deltas) if prof.score_deltas else 0.0
            sr = prof.total_search / tt
            sc = prof.total_search_catches / prof.total_search if prof.total_search else 0.0
            pr = prof.total_prime / tt
            cr = prof.total_carpet / tt
            acl = statistics.fmean(prof.carpet_lengths) if prof.carpet_lengths else 0.0
            tl = statistics.fmean(prof.time_lefts) if prof.time_lefts else 0.0
            f.write(f"{rank},{name},{prof.elo:.1f},{n},{prof.wins},{prof.losses},{prof.ties},"
                    f"{wr:.4f},{avg_d:.2f},{sr:.4f},{sc:.4f},{pr:.4f},{cr:.4f},{acl:.2f},{tl:.1f}\n")
    print(f"  ELO rankings: {elo_path}")

    # Save elite profiles JSON
    elite_json_path = args.output_dir / "elite_profiles.json"
    elite_data = []
    for ep in elite_profiles:
        elite_data.append({
            "name": ep.name,
            "elo": ep.elo,
            "match_count": ep.match_count,
            "win_rate": ep.win_rate,
            "avg_score": ep.avg_score,
            "avg_opp_score": ep.avg_opp_score,
            "avg_score_delta": ep.avg_score_delta,
            "median_score_delta": ep.median_score_delta,
            "prime_rate": ep.prime_rate,
            "carpet_rate": ep.carpet_rate,
            "search_rate": ep.search_rate,
            "plain_rate": ep.plain_rate,
            "search_per_game": ep.search_per_game,
            "search_conversion": ep.search_conversion,
            "avg_carpet_length": ep.avg_carpet_length,
            "carpet_per_game": ep.carpet_per_game,
            "avg_time_left": ep.avg_time_left,
            "median_time_left": ep.median_time_left,
            "time_pressure_rate": ep.time_pressure_rate,
            "avg_score_at_turn": ep.avg_score_at_turn,
            "worst_opponents": [{"opp": o, "loss_rate": lr, "n": n}
                               for o, lr, n in ep.worst_opponents],
            "best_opponents": [{"opp": o, "loss_rate": lr, "n": n}
                              for o, lr, n in ep.best_opponents],
        })
    elite_json_path.write_text(json.dumps(elite_data, indent=2))
    print(f"  Elite profiles: {elite_json_path}")

    # Save counter strategies JSON
    cs_path = args.output_dir / "counter_strategies.json"
    cs_path.write_text(json.dumps(counter_strategies, indent=2))
    print(f"  Counter strategies: {cs_path}")

    # Save bot roster
    roster_path = args.output_dir / "bot_roster.json"
    roster = {}
    for name, prof in sorted(profiles.items(), key=lambda x: -x[1].elo):
        if prof.match_count < 5:
            continue
        roster[name] = {
            "elo": round(prof.elo, 1),
            "matches": prof.match_count,
            "wins": prof.wins,
            "losses": prof.losses,
            "ties": prof.ties,
        }
    roster_path.write_text(json.dumps(roster, indent=2))
    print(f"  Bot roster: {roster_path}")

    total_time = time.time() - t_start
    print(f"\n✅ Pipeline complete in {total_time:.1f}s ({total_time/60:.1f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

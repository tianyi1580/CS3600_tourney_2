#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "tests"
AGENT_DIR = ROOT / "3600-agents" / "Yolanda"

SPEC_FILES = [
    ROOT / "docs" / "assignment_spec.md",
    ROOT / "docs" / "bot_plan_v4.md",
]

CORE_MODULES = [
    AGENT_DIR / "agent.py",
    AGENT_DIR / "tracking" / "belief.py",
    AGENT_DIR / "strategy" / "policy.py",
    AGENT_DIR / "infra" / "runtime_state.py",
    AGENT_DIR / "infra" / "time_manager.py",
]

MAJOR_FLAW_REPORT = ROOT / "logs" / "major_flaw_report.txt"
NEXT_STEPS_SUGGESTION = ROOT / "docs" / "next_steps_suggestion.txt"
M0_EVIDENCE_REPORT = ROOT / "docs" / "m0_discrepancy_evidence_report.md"


def run_cmd(
    cmd: list[str],
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_seconds,
        )
        return proc.returncode, proc.stdout
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        return 124, f"{output}\nCommand timed out after {timeout_seconds:.1f}s: {' '.join(cmd)}"


class Guard:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.logs: list[str] = []

    def fail(self, message: str) -> None:
        self.failures.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def log(self, message: str) -> None:
        self.logs.append(message)

    def stage_spec_lock(self) -> None:
        self.log("[1/7] Spec lock check")
        for spec in SPEC_FILES:
            if not spec.exists():
                self.fail(f"Missing required spec file: {spec}")

        if not TEST_DIR.exists():
            self.fail("Missing tests/ directory")
            return

        test_files = sorted(TEST_DIR.glob("test_*.py"))
        test_corpus = "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in test_files
        )

        required_references = {
            "search inclusion hazard": ["exclude_search", "SEARCH"],
            "tri-state parsing": ["None", "parse_search_tuple"],
            "belief reset parity": ["reset_after_capture", "belief"],
            "timing fallback": ["emergency", "allocation"],
            "M3 bounded adaptation": ["apply_adaptation", "infer_opponent_category", "adaptive_margin_delta"],
        }

        for topic, patterns in required_references.items():
            if not all(p in test_corpus for p in patterns):
                self.fail(f"Tests do not reference required topic '{topic}' with patterns {patterns}")

        required_tests: dict[str, set[str]] = {
            "test_discrepancy_contract.py": {
                "test_board_default_move_generation_excludes_search",
            },
            "test_policy_contract.py": {
                "test_parse_search_tuple_tristate",
                "test_apply_search_channels_obeys_tri_state_and_deduplicates",
            },
            "test_agent_contract.py": {
                "test_play_returns_legal_move",
            },
            "test_belief_engine.py": {
                "test_reset_after_capture_matches_cached_prior",
            },
            "test_time_manager.py": {
                "test_allocation_enters_emergency_near_floor",
            },
            "test_opponent_inference.py": {
                "test_infer_non_search_replay_matches_single_candidate",
            },
            "test_adaptation_clamps.py": {
                "test_confidence_below_floor_zeros_adaptation",
            },
            "test_adaptation_determinism.py": {
                "test_repeated_apply_adaptation_identical",
            },
        }
        for file_name, expected in required_tests.items():
            file_path = TEST_DIR / file_name
            if not file_path.exists():
                self.fail(f"Missing required test file: {file_name}")
                continue
            try:
                tree = ast.parse(file_path.read_text(encoding="utf-8", errors="ignore"))
            except Exception as exc:
                self.fail(f"Unable to parse {file_name}: {exc}")
                continue

            found = {
                node.name
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
            }
            missing = sorted(expected - found)
            if missing:
                self.fail(f"Missing required test cases in {file_name}: {missing}")

    def stage_lint_static(self) -> None:
        self.log("[2/7] Lint/static hygiene")
        targets = ["3600-agents", "engine", "workflows", "tests"]

        if shutil.which("ruff"):
            code, out = run_cmd(["ruff", "check", *targets])
            self.log(out.strip())
            if code != 0:
                self.fail("ruff check failed")
            return

        code, out = run_cmd([sys.executable, "-m", "compileall", *targets])
        self.log(out.strip())
        if code != 0:
            self.fail("compileall fallback failed")

    def stage_tests(self) -> None:
        self.log("[3/7] Unit and contract tests")
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{ROOT / 'engine'}:{ROOT / '3600-agents'}:{env.get('PYTHONPATH', '')}"
        code, out = run_cmd(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
            env=env,
        )
        self.log(out.strip())
        if code != 0:
            self.fail("unittest suite failed")

    def stage_coverage(self) -> None:
        self.log("[4/7] Coverage gate (>=85% core modules)")
        if not all(p.exists() for p in CORE_MODULES):
            self.warn("Core modules not all present; coverage gate skipped")
            return

        core_module_names = {
            "Yolanda.agent",
            "Yolanda.tracking.belief",
            "Yolanda.strategy.policy",
            "Yolanda.infra.runtime_state",
            "Yolanda.infra.time_manager",
        }

        try:
            import coverage  # noqa: F401
            use_coverage = True
        except Exception:
            use_coverage = False

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{ROOT / 'engine'}:{ROOT / '3600-agents'}:{env.get('PYTHONPATH', '')}"

        if use_coverage:
            src = "Yolanda.agent,Yolanda.tracking.belief,Yolanda.strategy.policy,Yolanda.infra.runtime_state,Yolanda.infra.time_manager"
            code, out = run_cmd(
                [
                    sys.executable,
                    "-m",
                    "coverage",
                    "run",
                    f"--source={src}",
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "tests",
                    "-p",
                    "test_*.py",
                ],
                env=env,
            )
            self.log(out.strip())
            if code != 0:
                if "cannot load module more than once per process" in out:
                    self.fail(
                        "Coverage execution failed due Python 3.14 numpy instrumentation incompatibility; "
                        "run the gate in a compatible environment and rerun quality_guard"
                    )
                    return
                self.warn("Coverage module execution failed; falling back to trace coverage")
                use_coverage = False
            else:
                cov_json = ROOT / ".coverage.json"
                code, out = run_cmd([sys.executable, "-m", "coverage", "json", "-o", str(cov_json)], env=env)
                self.log(out.strip())
                if code != 0 or not cov_json.exists():
                    self.warn("Coverage JSON export failed; falling back to trace coverage")
                    use_coverage = False
                else:
                    data = json.loads(cov_json.read_text(encoding="utf-8"))
                    pct = float(data.get("totals", {}).get("percent_covered", 0.0))
                    self.log(f"Coverage total: {pct:.2f}% (coverage module)")
                    if pct < 85.0:
                        self.fail(f"Coverage {pct:.2f}% is below required 85% floor")
                    return

        if use_coverage:
            return

        trace_cmd = [
            sys.executable,
            "-m",
            "trace",
            "--count",
            "--summary",
            "--coverdir",
            str(ROOT / ".tracecov"),
            "--module",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_*.py",
        ]
        code, out = run_cmd(trace_cmd, env=env)
        self.log(out.strip())
        if code != 0:
            if "cannot load module more than once per process" in out:
                self.fail(
                    "Trace coverage failed due Python 3.14 numpy instrumentation incompatibility; "
                    "run the gate in a compatible environment and rerun quality_guard"
                )
                return
            self.fail("Trace-based coverage fallback failed")
            return

        summary_pattern = re.compile(r"^\s*(\d+)\s+(\d+)%\s+(\S+)\s+\(([^)]+)\)$", re.MULTILINE)
        weighted_cov = 0.0
        weighted_lines = 0
        seen_modules: set[str] = set()
        for lines_s, pct_s, module_name, _path in summary_pattern.findall(out):
            if module_name not in core_module_names:
                continue
            lines = int(lines_s)
            pct = float(pct_s)
            weighted_lines += lines
            weighted_cov += lines * pct
            seen_modules.add(module_name)

        missing = sorted(core_module_names - seen_modules)
        if missing:
            self.fail(
                f"Trace summary did not map expected package module names ({missing}); "
                "coverage gate cannot be satisfied in this environment"
            )
            return
        if weighted_lines == 0:
            self.fail("Trace coverage found zero executable lines for core modules")
            return

        weighted_pct = weighted_cov / weighted_lines
        self.log(f"Coverage total: {weighted_pct:.2f}% (trace fallback)")
        if weighted_pct < 85.0:
            self.fail(f"Coverage {weighted_pct:.2f}% is below required 85% floor")

    def stage_architecture(self) -> None:
        self.log("[5/7] Architecture constraints")
        if not AGENT_DIR.exists():
            self.fail("Missing Yolanda agent package")
            return

        all_files = {}
        for p in AGENT_DIR.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            all_files[p.name] = p.read_text(encoding="utf-8", errors="ignore")

        agent_code = all_files.get("agent.py", "")
        for required_import in ("BeliefEngine", "PolicyEngine", "RuntimeState", "TimeManager"):
            if required_import not in agent_code:
                self.fail(f"agent.py missing delegation import/reference: {required_import}")

        for forbidden_token in ("def score_non_search", "def score_search", "class BeliefEngine"):
            if forbidden_token in agent_code:
                self.fail(f"agent.py contains logic that should live in dedicated modules: {forbidden_token}")

        belief_code = all_files.get("belief.py", "")
        for method_name in ("def predict", "def update", "def reset_after_capture", "def topk"):
            if method_name not in belief_code:
                self.fail(f"belief.py missing required method: {method_name}")

        policy_code = all_files.get("policy.py", "")
        for method_name in (
            "def generate_candidates",
            "def score_non_search",
            "def score_search",
            "def select_action",
        ):
            if method_name not in policy_code:
                self.fail(f"policy.py missing required method: {method_name}")
        if "Move.search" not in policy_code and "exclude_search=False" not in policy_code:
            self.fail("policy.py does not contain explicit search candidate path")

        runtime_code = all_files.get("runtime_state.py", "")
        for required_field in (
            "mu_ev",
            "sigma_ev",
            "mu_t",
            "sigma_t",
            "fallback_move",
            "observed_turns",
        ):
            if required_field not in runtime_code:
                self.fail(f"runtime_state.py missing required field hint: {required_field}")

        network_pattern = re.compile(r"^\s*(?:import|from)\s+(socket|requests|urllib)\b", re.MULTILINE)
        for file_name, file_data in all_files.items():
            if network_pattern.search(file_data):
                self.fail(f"Network import detected in {file_name}")

    def stage_runtime_smoke(self) -> None:
        self.log("[6/7] Runtime readiness smoke")
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{ROOT / 'engine'}:{ROOT / '3600-agents'}:{env.get('PYTHONPATH', '')}"

        code, out = run_cmd(
            [sys.executable, "engine/run_local_agents.py", "Yolanda", "Yolanda"],
            env=env,
            timeout_seconds=120.0,
        )
        self.log(out.strip())
        if code != 0:
            sandbox_blocked = (
                "PermissionError: [Errno 1] Operation not permitted" in out
                and ("sysctl(KERN_PROC_ALL)" in out or "originated from sysctl()" in out)
            )
            if sandbox_blocked:
                self.warn("Local runtime smoke skipped due sandbox psutil process-list restrictions")
            else:
                self.fail("Local runtime smoke failed")

        if platform.system() != "Linux":
            self.warn("Restricted-mode seccomp smoke skipped (non-Linux host)")
            return

        code, out = run_cmd(
            [
                sys.executable,
                "-c",
                (
                    "import os,sys;"
                    "sys.path.insert(0,'engine');"
                    "import gameplay;"
                    "ok,msg=gameplay.validate_submission(os.path.join(os.getcwd(),'3600-agents'),'Yolanda',limit_resources=True,use_gpu=False);"
                    "print(ok);print(msg)"
                ),
            ],
            env=env,
            timeout_seconds=120.0,
        )
        self.log(out.strip())
        if code != 0:
            self.fail("Restricted validation command failed")
            return
        if "True" not in out.splitlines()[:2]:
            self.fail("Restricted validation did not return success=True")

    def stage_reporting(self) -> int:
        self.log("[7/7] Reporting")
        self._write_m0_evidence_report()
        if self.failures:
            MAJOR_FLAW_REPORT.write_text(
                "Quality Guard: MAJOR FLAWS DETECTED\n\n"
                + "\n".join(f"- {f}" for f in self.failures)
                + "\n\nRemediation path:\n"
                + "1) Resolve failing stages in order.\n"
                + "2) Re-run workflows/quality_guard.py.\n"
                + "3) Do not advance milestone until guard is clean.\n",
                encoding="utf-8",
            )
            if NEXT_STEPS_SUGGESTION.exists():
                NEXT_STEPS_SUGGESTION.unlink()
            return 1

        NEXT_STEPS_SUGGESTION.write_text(
            "Quality Guard: PASS\n\n"
            "Suggested next step: advance from M0 toward M1 by expanding belief parity tests "
            "(search-reset parity under non-identity transition matrices) and adding strict_240 stress batches.\n",
            encoding="utf-8",
        )
        if MAJOR_FLAW_REPORT.exists():
            MAJOR_FLAW_REPORT.unlink()
        return 0

    def _write_m0_evidence_report(self) -> None:
        lines: list[str] = []
        lines.append("# M0 Discrepancy Evidence Report")
        lines.append("")
        lines.append("Generated by `workflows/quality_guard.py`.")
        lines.append("")
        lines.append("## Scope")
        lines.append("- M0 correctness foundation evidence for legality/search-inclusion/tri-state coverage.")
        lines.append("- Ground-truth precedence: `assignment_spec.md`, then `bot_plan_v4.md`.")
        lines.append("")
        lines.append("## Gate Status")
        if self.failures:
            lines.append("- Result: **FAIL**")
        else:
            lines.append("- Result: **PASS**")
        lines.append(f"- Failure count: `{len(self.failures)}`")
        lines.append(f"- Warning count: `{len(self.warnings)}`")
        lines.append("")
        lines.append("## Logged Stages")
        for item in self.logs:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## Required M0 Topics")
        lines.append("- Search inclusion hazard (`exclude_search=True` default): validated by `tests/test_discrepancy_contract.py` and `tests/test_policy_contract.py`.")
        lines.append("- Tri-state search parsing (`True/False/None`): validated by `tests/test_policy_contract.py`.")
        lines.append("- Legality and safe action fallback: validated by `tests/test_agent_contract.py` and runtime smoke stage.")
        lines.append("- Belief reset parity + normalization checks: validated by `tests/test_belief_engine.py`.")
        lines.append("")
        lines.append("## Failures")
        if self.failures:
            for failure in self.failures:
                lines.append(f"- {failure}")
        else:
            lines.append("- None")
        lines.append("")
        lines.append("## Warnings")
        if self.warnings:
            for warning in self.warnings:
                lines.append(f"- {warning}")
        else:
            lines.append("- None")
        lines.append("")
        M0_EVIDENCE_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run(self) -> int:
        self.stage_spec_lock()
        self.stage_lint_static()
        self.stage_tests()
        self.stage_coverage()
        self.stage_architecture()
        self.stage_runtime_smoke()
        code = self.stage_reporting()

        print("\n".join(self.logs))
        if self.warnings:
            print("\nWarnings:")
            for warning in self.warnings:
                print(f"- {warning}")
        if self.failures:
            print("\nFailures:")
            for failure in self.failures:
                print(f"- {failure}")
        else:
            print("\nAll quality gates passed.")

        return code


if __name__ == "__main__":
    raise SystemExit(Guard().run())

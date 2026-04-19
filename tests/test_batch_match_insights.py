from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from workflows.batch_match_insights import (
    ParseIssue,
    NormalizedMatch,
    _coerce_bool_series,
    _compute_deficit_onset,
    _compute_transition_patterns,
    _derive_map_seed,
    _format_threshold_key,
    _phase_ranges,
    _top_turning_points,
    build_insights,
    normalize_match,
    render_markdown,
    run_pipeline,
    write_csv,
)


ROOT = Path(__file__).resolve().parents[1]


class BatchMatchInsightsTests(unittest.TestCase):
    def _synthetic_match(
        self,
        match_id: str,
        left_behind: list[str],
        rat_caught: list[bool],
        deltas: list[float],
    ) -> NormalizedMatch:
        a_points = [delta for delta in deltas]
        b_points = [0.0 for _ in deltas]
        return NormalizedMatch(
            source_path=f"/tmp/{match_id}.json",
            match_id=match_id,
            schema_version="m2",
            turn_count=max(1, len(deltas) - 1),
            result=0,
            reason="POINTS",
            timeline={
                "a_points": a_points,
                "b_points": b_points,
                "a_time_left": [100.0 for _ in deltas],
                "b_time_left": [100.0 for _ in deltas],
                "a_turns_left": list(reversed(range(len(deltas)))),
                "b_turns_left": list(reversed(range(len(deltas)))),
                "rat_caught": rat_caught,
                "left_behind": left_behind,
            },
            positions={"a_pos": [], "b_pos": [], "rat_position_history": []},
            events={"blocked_or_trapdoors": [], "new_carpets": [], "errlog_a": "", "errlog_b": ""},
            extras={},
            cohort={"source_group": "synthetic", "schema_version": "m2"},
        )

    def test_phase_ranges_cover_full_length(self) -> None:
        ranges = _phase_ranges(10)
        self.assertEqual(ranges["early"], (0, 3))
        self.assertEqual(ranges["mid"], (3, 6))
        self.assertEqual(ranges["late"], (6, 10))

    def test_transition_extraction_and_sorting(self) -> None:
        win = self._synthetic_match(
            "w1",
            ["search", "prime", "plain", "search"],
            [False, False, False, True],
            [0, 1, 2, 3],
        )
        loss = self._synthetic_match(
            "l1",
            ["search", "prime", "search", "prime"],
            [False, False, False, False],
            [0, -1, -2, -3],
        )
        payload = _compute_transition_patterns([win, loss], top_n=5, min_support=1)
        self.assertTrue(payload["top_gaps"])
        first = payload["top_gaps"][0]
        self.assertIn("transition", first)
        self.assertIn("gap_abs", first)
        self.assertIn("support", first)

    def test_transition_patterns_respect_min_support(self) -> None:
        win = self._synthetic_match(
            "w2",
            ["prime", "search", "plain", "prime"],
            [False, False, False, False],
            [0, 1, 2, 3],
        )
        loss = self._synthetic_match(
            "l2",
            ["prime", "search", "prime", "search"],
            [False, False, False, False],
            [0, -1, -2, -3],
        )
        payload = _compute_transition_patterns([win, loss], top_n=10, min_support=3)
        self.assertEqual(payload["min_support"], 3)
        self.assertTrue(payload["dropped_low_support"] > 0)
        self.assertTrue(all(row["support"] >= 3 for row in payload["top_gaps"]))

    def test_deficit_onset_detection_known_values(self) -> None:
        loss = self._synthetic_match(
            "l2",
            ["plain", "plain", "plain", "plain"],
            [False, False, False, False],
            [0, -3, -6, -11],
        )
        out = _compute_deficit_onset([loss], thresholds=[-5.0, -10.0])
        self.assertAlmostEqual(out[_format_threshold_key(-5.0)]["losses"]["onset_rate"], 1.0)
        self.assertAlmostEqual(out[_format_threshold_key(-10.0)]["losses"]["median_turn"], 3.0)

    def test_deficit_onset_preserves_non_integer_threshold_keys(self) -> None:
        loss = self._synthetic_match(
            "l3",
            ["plain", "plain", "plain", "plain"],
            [False, False, False, False],
            [0, -10.3, -10.7, -11.2],
        )
        out = _compute_deficit_onset([loss], thresholds=[-10.1, -10.9])
        self.assertIn(_format_threshold_key(-10.1), out)
        self.assertIn(_format_threshold_key(-10.9), out)
        self.assertNotEqual(_format_threshold_key(-10.1), _format_threshold_key(-10.9))

    def test_turning_points_sorted_worst_first(self) -> None:
        match = self._synthetic_match(
            "tp1",
            ["plain", "search", "prime", "plain", "search"],
            [False, False, False, False, False],
            [0, -1, -4, -2, -7],
        )
        rows = _top_turning_points(match, k=2)
        self.assertEqual(len(rows), 2)
        self.assertLessEqual(rows[0]["delta_change"], rows[1]["delta_change"])
        self.assertIn("phase", rows[0])

    def test_normalize_match_handles_current_dataset_shape(self) -> None:
        sample_path = sorted((ROOT / "data" / "matches" / "yolanda_prime_v1_2").glob("*.json"))[0]
        match, issues = normalize_match(sample_path)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.schema_version, "m2")
        self.assertIn("a_pos", match.positions)
        self.assertIn("b_pos", match.positions)
        self.assertEqual(len(match.timeline["a_points"]), match.turn_count + 1)
        self.assertTrue(all(issue.severity != "fatal" for issue in issues))

    def test_build_insights_confidence_labels_present(self) -> None:
        match_paths = sorted((ROOT / "data" / "matches").rglob("*.json"))[:10]
        normalized = []
        for path in match_paths:
            match, _ = normalize_match(path)
            if match is not None:
                normalized.append(match)
        insights = build_insights(normalized, n_min=5)
        all_cohort = next(c for c in insights["cohorts"] if c["cohort"] == "all")
        self.assertIn(all_cohort["outcome"]["win_confidence"], {"high_confidence", "medium_confidence", "insufficient_data"})
        self.assertIn(all_cohort["outcome"]["delta_confidence"], {"high_confidence", "medium_confidence", "insufficient_data"})
        self.assertIn("trajectory_robustness", all_cohort)
        self.assertIn("behavior_contrasts", all_cohort)
        self.assertIn("cohort_type", all_cohort)

    def test_build_insights_includes_stratified_cohorts(self) -> None:
        match_paths = sorted((ROOT / "data" / "matches" / "yolanda_prime_v1_2").glob("*.json"))[:12]
        normalized = []
        for path in match_paths:
            match, _ = normalize_match(path)
            if match is not None:
                normalized.append(match)
        insights = build_insights(
            normalized,
            n_min=4,
            stratify_by=["opponent_archetype", "opening_family"],
            max_cohorts=4,
            rare_min_support=2,
        )
        self.assertTrue(any(c.get("cohort_type") == "segment" for c in insights["cohorts"]))
        segment = next(c for c in insights["cohorts"] if c.get("cohort_type") == "segment")
        self.assertIn("cohort_dimensions", segment)
        self.assertIn("opponent_archetype", segment["cohort_dimensions"])
        self.assertIn("opening_family", segment["cohort_dimensions"])

    def test_win_rate_uses_final_scores_not_result_flag(self) -> None:
        match_paths = sorted((ROOT / "data" / "matches" / "yolanda_prime_v1_2").glob("*.json"))
        normalized = []
        for path in match_paths:
            match, _ = normalize_match(path)
            if match is not None:
                normalized.append(match)
        insights = build_insights(normalized, n_min=8)
        all_cohort = next(c for c in insights["cohorts"] if c["cohort"] == "all")
        expected_wins = sum(1 for m in normalized if m.timeline["a_points"][-1] > m.timeline["b_points"][-1])
        expected_losses = sum(1 for m in normalized if m.timeline["a_points"][-1] < m.timeline["b_points"][-1])
        self.assertEqual(all_cohort["outcome"]["wins"], expected_wins)
        self.assertEqual(all_cohort["outcome"]["losses"], expected_losses)
        self.assertAlmostEqual(all_cohort["outcome"]["win_rate"], expected_wins / len(normalized))

    def test_run_pipeline_writes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "out"
            rc = run_pipeline(
                ROOT / "data" / "matches",
                output_dir,
                n_min=4,
                deficit_thresholds=[-5.0, -10.0, -15.0],
                turning_point_k=3,
                top_transitions=8,
                transition_min_support=2,
                max_fatal_rate=0.0,
            )
            self.assertEqual(rc, 0)

            parse_report = output_dir / "parse_report.json"
            summary = output_dir / "insights_summary.json"
            report = output_dir / "insights_report.md"
            cohort = output_dir / "cohort_breakdown.csv"
            self.assertTrue(parse_report.is_file())
            self.assertTrue(summary.is_file())
            self.assertTrue(report.is_file())
            self.assertTrue(cohort.is_file())

            payload = json.loads(summary.read_text())
            self.assertIn("cohorts", payload)
            self.assertIn("global_actions", payload)
            all_cohort = next(c for c in payload["cohorts"] if c["cohort"] == "folder:matches")
            self.assertIn("phase_split", all_cohort)
            self.assertIn("transition_patterns", all_cohort)
            self.assertIn("deficit_onset", all_cohort)
            self.assertIn("turning_points_summary", all_cohort)

    def test_run_pipeline_fails_when_fatal_rate_exceeds_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            bad_path = tmp_root / "bad.json"
            bad_path.write_text("{")
            output_dir = tmp_root / "out"
            rc = run_pipeline(
                tmp_root,
                output_dir,
                n_min=2,
                deficit_thresholds=[-5.0],
                turning_point_k=2,
                top_transitions=4,
                transition_min_support=1,
                max_fatal_rate=0.0,
            )
            self.assertEqual(rc, 2)
            parse_payload = json.loads((output_dir / "parse_report.json").read_text())
            self.assertEqual(parse_payload["fatal_count"], 1)
            self.assertEqual(parse_payload["fatal_rate"], 1.0)

    def test_bool_series_string_false_does_not_coerce_true(self) -> None:
        issues: list[ParseIssue] = []
        out = _coerce_bool_series(["False", "0", "", "no", "nonsense", "True", 1, 0], "rat_caught", issues)
        self.assertEqual(out, [False, False, False, False, False, True, True, False])
        self.assertTrue(any("invalid string bool" in issue.message for issue in issues))

    def test_map_seed_fingerprint_includes_spawn_from_events(self) -> None:
        a = self._synthetic_match("ms1", ["plain", "plain"], [False, False], [0, 1])
        b = self._synthetic_match("ms2", ["plain", "plain"], [False, False], [0, 1])
        a.events["blocked_or_trapdoors"] = [[1, 1], [2, 2]]
        b.events["blocked_or_trapdoors"] = [[1, 1], [2, 2]]
        a.events["spawn_a"] = [0, 0]
        a.events["spawn_b"] = [8, 8]
        b.events["spawn_a"] = [1, 0]
        b.events["spawn_b"] = [8, 8]
        self.assertNotEqual(_derive_map_seed(a), _derive_map_seed(b))

    def test_markdown_preserves_non_integer_threshold_display(self) -> None:
        match = self._synthetic_match("md1", ["plain", "plain", "plain"], [False, False, False], [0, -1, -2])
        insights = build_insights([match], n_min=1, deficit_thresholds=[-10.5, -7.25])
        markdown = render_markdown(insights)
        self.assertIn("`-10.5, -7.25`", markdown)

    def test_write_csv_uses_runtime_thresholds(self) -> None:
        match = self._synthetic_match("csv1", ["plain", "plain", "plain"], [False, False, False], [0, -6, -12])
        insights = build_insights([match], n_min=1, deficit_thresholds=[-6.5, -12.25])
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "out.csv"
            write_csv(insights, csv_path)
            header = csv_path.read_text().splitlines()[0]
            self.assertIn("threshold_-6.5_onset_rate", header)
            self.assertIn("threshold_-12.25_median_turn", header)
            self.assertIn("mean_time_in_deficit_-6.5", header)
            self.assertIn("recovery_rate_after_cross_-12.25", header)
            self.assertNotIn("threshold_-10_onset_rate", header)

    def test_transition_payload_declares_turn_weighted_normalization(self) -> None:
        win = self._synthetic_match("tw1", ["plain", "search", "plain"], [False, False, False], [0, 1, 2])
        loss = self._synthetic_match("tw2", ["plain", "prime", "plain"], [False, False, False], [0, -1, -2])
        payload = _compute_transition_patterns([win, loss], top_n=5, min_support=1)
        self.assertEqual(payload["normalization"], "turn_weighted")


if __name__ == "__main__":
    unittest.main()

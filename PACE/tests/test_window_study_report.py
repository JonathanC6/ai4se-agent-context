import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from benchmarks.window_study import GROUPS, study_rows
from benchmarks.window_study_report import main, report
from benchmarks.webwalkerqa import DATA_SHA, REVISION
from pace.records import write_result


class WindowReportTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)
        self.dataset = [dict(question="Q", info=dict(type="single_source", source_website=["https://example.org"]))]
        self.groups = {"pace-delayed": ("pace", "window", 0.8)}
        self.cfg = dict(rows=[1], dataset=REVISION, sha256=DATA_SHA, budget=6000,
                        provider_input_budget=80000, max_steps=24, grading_version="legacy-v1",
                        actor_budget_protocol="per-response-v2", token_counter="labhuan-visible-v1",
                        pressure_mode="window", compression_start_ratio=0.8, arms=["pace"])

    def save(self, label, *, actual=17000, more_action=False, overhead=0, cfg=None):
        folder = self.path / label
        cfg = cfg or self.cfg
        arm, = cfg["arms"]
        write_result(folder / "config.json", cfg)
        rejected = actual > self.cfg["provider_input_budget"]
        window = dict(phase="full_history", full_input_estimate=100, current_input_estimate=100, organized_input_estimate=100,
                      activation_step=None, first_organization_step=None)
        pressure = 100 / cfg["budget"] if cfg["compression_start_ratio"] is None else 0
        step = dict(step=1, action=dict(tool="finish"), chunks=[], input_tokens_estimate=100, pressure=pressure,
                    input_tokens_actual=actual, input_count_error=100-actual, window=window)
        final_usage = dict(requests=1, prompt_tokens=actual, completion_tokens=1, total_tokens=actual+1)
        r = dict(steps=[step], actor_episode_id=label, status="budget_exceeded" if rejected else "finished",
                 answer=None if rejected else "A", grade=dict(correct=not rejected, version="legacy-v1"),
                 question="Q", row=1, arm=arm, repeat=1, input_count_method="labhuan-visible-v1",
                 history=[dict(kind="search",observation="[]")] if more_action else [], usage=dict(actor=final_usage))
        write_result(folder / f"rep-1/{arm}/row-1.json", r)
        event = dict(job=[1, 1, arm], role="actor", episode_id=label, decision_step=1, format_attempt=1,
                     input_tokens_estimate=100, prompt_tokens=actual, completion_tokens=1, total_tokens=actual+1)
        events = [event]
        if overhead:
            events.insert(0, dict(event, episode_id="previous", prompt_tokens=overhead-1, total_tokens=overhead))
        (folder / "usage.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))

    def make_report(self):
        with patch("benchmarks.window_study_report.study_rows", return_value=[1]):
            return report(self.dataset, self.path, self.groups)

    def test_replacement_preserves_cohort_balance_and_original_list(self):
        info = dict(type="multi_source", lang="en", difficulty_level="hard")
        dataset = [dict(info=info), dict(info=info), dict(info=dict(info, type="single_source"))]
        with patch("benchmarks.window_study.cohort", return_value=[1]):
            self.assertEqual(study_rows(dataset, [[1, 2]]), [2])
            self.assertEqual(study_rows(dataset), [1])
            for replacement in ([1, 3], [2, 3], [1, 1], [1, 0]):
                with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                    study_rows(dataset, [replacement])
            with self.assertRaisesRegex(ValueError, "only once"):
                study_rows(dataset, [[1, 2], [1, 2]])

    def test_visible_window_and_gateway_ceiling_are_separate(self):
        self.save("pace-delayed", overhead=100)
        g = self.make_report()["groups"]["pace-delayed"]
        self.assertEqual((g["correct"], g["never_activated"], g["executed_peak"]), (1, 1, 17000))
        self.assertEqual((g["scored_tokens"], g["ledger_tokens"]), (17001, 17101))

    def test_rejected_response_does_not_count_as_an_executed_step(self):
        self.save("pace-delayed", actual=90000)
        g = self.make_report()["groups"]["pace-delayed"]
        self.assertEqual((g["correct"], g["steps"], g["executed_steps"], g["budget_stops"]), (0, 1, 0, {"gateway": 1}))
        self.save("pace-delayed", actual=90000, more_action=True)
        with self.assertRaisesRegex(ValueError, "over-budget"):
            self.make_report()

    def test_inconsistent_settings_prevent_paired_report(self):
        self.save("pace-delayed")
        self.groups["pace-window"] = ("pace", "window", None)
        self.save("pace-window", cfg=dict(self.cfg, compression_start_ratio=None, provider_input_budget=96000))
        with self.assertRaisesRegex(ValueError, "shared configuration"):
            self.make_report()

    def test_pressure_report_uses_only_five_selected_groups(self):
        selected = [k for k, (_, _, gate) in GROUPS.items() if gate is None]
        for label in selected:
            arm, mode, gate = GROUPS[label]
            self.save(label, cfg=dict(self.cfg, arms=[arm], pressure_mode=mode, compression_start_ratio=gate))
        write_result(self.path / "comparison.json", {"previous": True})
        args = ["report", "--out", str(self.path), "--groups", *selected]
        with patch("sys.argv", args), patch("benchmarks.window_study_report.study_rows", return_value=[1]), \
             patch("benchmarks.window_study_report.load_dataset", return_value=self.dataset), redirect_stdout(StringIO()):
            main()
        result = json.loads((self.path / "pressure-comparison.json").read_text())
        self.assertEqual(set(result["groups"]), set(selected))
        self.assertEqual(set(result["rows"]["1"]), set(selected))
        self.assertFalse(any("delayed" in pair for pair in result["paired"]))
        self.assertEqual(json.loads((self.path / "comparison.json").read_text()), {"previous": True})

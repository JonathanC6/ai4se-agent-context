import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from benchmarks.actor_budget import PROTOCOL
from benchmarks.verified_research20 import ARMS, compare
from benchmarks.webwalkerqa import DATA_SHA, REVISION
from pace.records import write_result


class VerifiedComparisonTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name)
        self.old, self.new = path / "old", path / "new"
        self.dataset = [dict(question="Q", info=dict(source_website=["https://example.org/"],
                                                      type="single_source"))]
        self.config = dict(rows=[1], dataset=REVISION, sha256=DATA_SHA, budget=16000, max_steps=24,
                           grading_version="legacy-v1", token_counter="test")

    def save(self, folder, arm, strict=False, overrun=False):
        path = folder / arm
        cfg = dict(self.config, arms=[arm])
        if strict:
            cfg["actor_budget_protocol"] = PROTOCOL
        write_result(path / "config.json", cfg)
        counts = [16500, 110, 120] if overrun else [110, 120]
        turns = [dict(kind="visit", observation=json.dumps([dict(read=True, url="https://example.org/")]))]
        steps = [dict(step=i, input_tokens_actual=a, input_tokens_estimate=100,
                      input_count_error=100 - a, action={}, chunks=[]) for i, a in enumerate([110, 120], 1)]
        r = dict(row=1, arm=arm, repeat=1, question="Q", answer="A", status="finished", history=turns,
                 steps=steps, grade={"version":"legacy-v1", "correct":True}, input_count_method="test",
                 usage={"actor": dict(requests=len(counts), prompt_tokens=sum(counts), completion_tokens=len(counts),
                                      total_tokens=sum(counts) + len(counts))})
        if strict:
            r["actor_episode_id"] = "strict-id"
        write_result(path / f"rep-1/{arm}/row-1.json", r)
        events = []
        for i, value in enumerate(counts, 1):
            e = dict(role="actor", job=[1, 1, arm], prompt_tokens=value, completion_tokens=1, total_tokens=value+1)
            if strict:
                e.update(episode_id="strict-id", decision_step=i, format_attempt=1, input_tokens_estimate=100)
            events.append(json.dumps(e))
        (path / "usage.jsonl").write_text("\n".join(events) + "\n")

    def compare(self):
        with patch("benchmarks.verified_research20.cohort", return_value=[1]), \
             patch("benchmarks.verified_research20.retry_token_delta", return_value=5):
            return compare(self.dataset, self.old, self.new)

    def test_prefix_recovery_excludes_page_read_after_hidden_overrun(self):
        self.save(self.old, "react", overrun=True)
        report = self.compare()
        result, = report["rows"]
        self.assertEqual((result["correct"], result["any_hit"], result["steps"], result["history_count"]),
                         (False, False, 1, 0))
        self.assertEqual(result["stop_reason"], "provider")
        self.assertEqual(report["pending"]["pace"], [1])
        self.assertEqual(report["billed"]["original"]["total"]["requests"], 3)
        self.assertFalse(self.new.exists())

    def test_strict_only_fills_missing_and_counts_both_ledgers_once(self):
        for arm in ARMS:
            self.save(self.new, arm, strict=True)
        self.save(self.old, "react")
        report = self.compare()
        self.assertEqual([r["source"] for r in report["rows"]], ["original-replay", "strict-live", "strict-live"])
        self.assertTrue(all(r["all_hit"] for r in report["rows"]))
        self.assertEqual(report["billed"]["original"]["total"]["requests"], 2)
        self.assertEqual(report["billed"]["strict"]["total"]["requests"], 6)

    def test_dependency_only_config_diff_blocks_report(self):
        self.save(self.old, "react")
        self.save(self.new, "dag-pace", strict=True)
        file = self.new / "dag-pace/config.json"
        write_result(file, dict(json.loads(file.read_text()), horizon=12))
        with self.assertRaisesRegex(ValueError, "settings differ"):
            self.compare()

import json
import unittest
from unittest.mock import patch

from benchmarks.source_evidence import SourceEvidence
from pace.agent import Tool, run
from pace.evidence import check_draft
from pace.memory import Memory, Summaries
from pace.policy import Settings
from pace.providers import Utf8Counter


class EvidenceV2Tests(unittest.TestCase):
    def test_new_pressure_bounded_in_empty_and_full_windows(self):
        settings = Settings(horizon=20, budget=6000, pressure_mode="evidence-v2")
        self.assertAlmostEqual(settings.pressure(24, 1200), .36)
        self.assertAlmostEqual(settings.pressure(10, 3000), .625)
        self.assertEqual(settings.pressure(1, 8000), 1)
        self.assertEqual(settings.pressure(24, 0), 0)

    def test_recovery_even_if_actor_declares_no_gap(self):
        visit = lambda _: json.dumps([dict(read=True, source_id="S1", extraction="Date omitted")])
        tools = {"visit": Tool("open", visit), "reread": Tool("recover", lambda _: "The date was March 14.")}
        actions = iter([dict(tool="visit", args={}), dict(tool="finish", args=dict(answer="Date unknown", missing_facts=[])),
                        dict(tool="finish", args=dict(answer="March 14", missing_facts=[]))])
        with Memory(lambda _: [1], lambda _: Summaries("detail", "brief")) as memory:
            result = run("Which date?", tools, lambda _: next(actions), memory, Settings(20), Utf8Counter(), 3,
                         coverage_check=lambda _: dict(target="S1", goal="exact event date"))
        self.assertEqual(result["answer"], "March 14")
        self.assertEqual(result["steps"][1]["recovery"], dict(trigger="automatic", tool="reread", ok=True))
        self.assertEqual(len(result["steps"]), 3)

    def test_recovery_uses_only_eligible_targets(self):
        entries = [dict(chunk_id=2, compressed=True, sources=[])]
        def decide(target):
            return check_draft("Who?", {"answer": "Unknown"}, entries, lambda _: dict(target=target, goal="name"))
        self.assertEqual(decide("C2"), ("glimpse", {"ids": [2]}, "name"))
        for target in ("C1", "S1"):
            with self.assertRaises(ValueError):
                decide(target)

    def test_goal_only_reread_can_reach_late_chinese_evidence(self):
        text = ("会议日程。" * 11000) + "基金项目的总金额是三万元。"
        with patch("benchmarks.source_evidence.extract_page", side_effect=lambda api, u, g, t, s, e: t[s:e][-50:]):
            evidence = SourceEvidence(None, rank_rereads=True)
            source = evidence.remember("https://example.org", text, 0, 24000)["source_id"]
            row = json.loads(evidence.reread(dict(source_id=source, goal="基金总金额")))
            self.assertGreater(row["window"][0], 0)
            self.assertIn("三万元", row["extraction"])
            row = json.loads(evidence.reread(dict(source_id=source, goal="基金总金额", offset=0)))
            self.assertEqual(row["window"][0], 0)

    def test_default_reread_of_short_page_includes_text_before_first_visit_offset(self):
        with patch("benchmarks.source_evidence.extract_page", side_effect=lambda api, u, g, t, s, e: t[s:e]):
            evidence = SourceEvidence(None, rank_rereads=True)
            text = "date: March 14. Venue details follow."
            source = evidence.remember("https://example.org", text, 16, len(text))["source_id"]
            row = json.loads(evidence.reread(dict(source_id=source, goal="date")))
            self.assertEqual(row["window"], [0, len(text)])
            self.assertIn("March 14", row["extraction"])

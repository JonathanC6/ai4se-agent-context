import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from benchmarks import webwalker_dynamic20 as dyn


class DynamicSearchTests(unittest.TestCase):
    def test_preserves_official_deadline_and_drops_answer_key(self):
        official = dict(title="Annual meeting dates", url="https://example.org/datasets/meetings",
                        snippet="The deadline is November 22.")
        leaked = dict(title="Benchmark mirror", url="https://example.org/WebWalkerQA",
                      snippet="Question and answer")
        copy = dict(title="QA collection", url="https://example.net/qa",
                    snippet='Question: How many chairs? Answer: Seven')
        with patch.object(dyn,"question_signatures",return_value=[dyn.normalized("How many chairs?")]):
            response = dyn.filtered("deadlines", [leaked, official, copy])
        self.assertEqual(response["results"], [official])
        self.assertEqual(len(response["excluded"]), 2)

    def test_same_query_returns_identical_cards_across_episodes(self):
        with TemporaryDirectory() as tmp, patch.object(dyn, "OUT", Path(tmp)):
            for q in ("meeting", "2024 schedule"):
                row = dict(url="https://example.org/" + q.split()[0], title=q, snippet="official agenda")
                dyn.write_result(dyn.OUT / "search" / f"{dyn.key(q)}.result.json", dyn.filtered(q,[row]))
            a = dyn.DynamicBrowser("https://example.org/", None, 1)
            b = dyn.DynamicBrowser("https://example.org/", None, 2)
            self.assertEqual(a.search({"query":"meeting"}), b.search({"query":"meeting"}))
            self.assertNotEqual(a.search({"query":"meeting"}), a.search({"query":"2024 schedule"}))
            self.assertIn("https://example.org/2024", a.allowed)

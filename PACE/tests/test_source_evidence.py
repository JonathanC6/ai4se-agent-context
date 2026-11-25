import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarks.paper_pilot import FullHistory
from benchmarks.source_evidence import SourceEvidence
from pace.agent import run, Tool
from pace.memory import Memory, Summaries
from pace.policy import Settings
from pace.providers import Utf8Counter


class SourceEvidenceTests(unittest.TestCase):
    def test_exact_snapshot_and_unseen_late_passage(self):
        text = "x" * 25000 + "Funding: April 2022"
        def extract(api, url, goal, page, start, end):
            self.assertIn("Funding: April 2022", page[start:end])
            return "April 2022"
        with tempfile.TemporaryDirectory() as tmp, patch("benchmarks.source_evidence.extract_page", extract):
            store = SourceEvidence(None, Path(tmp))
            a = store.remember("https://example.org", text, 0, 24000)
            b = store.remember("https://example.org", "revised", 0, 7)
            self.assertNotEqual(a["source_id"], b["source_id"])
            self.assertEqual((Path(tmp) / (a["text_sha256"] + ".txt")).read_text(), text)
            res = json.loads(store.reread(dict(source_id=a["source_id"], goal="funding", find="Funding")))
            self.assertIn("Funding: April 2022", res["excerpt"])
            self.assertEqual(res["extraction"], "April 2022")
            self.assertEqual(a["text_sha256"], res["text_sha256"])

    def test_targeted_glimpse_and_reread_recover_omitted_fact(self):
        raw = "The project started on April 4."
        def extract(api, url, goal, page, start, end):
            return page[start:end]
        with patch("benchmarks.source_evidence.extract_page", extract):
            store = SourceEvidence(None)
            meta = store.remember("https://example.org", raw, 0, len(raw))
            visit = lambda _: json.dumps([dict(meta, read=True, extraction="Project described; date omitted.")])
            tools = {"visit": Tool("opens page", visit), "reread": store.tool()}
            for mode in ("react", "pace"):
                actions = iter([dict(tool="visit", args={}),
                                dict(tool="reread", args=dict(source_id="S1",goal="project start"))
                                if mode == "react" else dict(tool="glimpse", args=dict(ids=[1],goal="project start"))])
                def actor(messages):
                    action = next(actions, None)
                    if action:
                        return action
                    self.assertIn("The project started on April 4.", messages[1]["content"])
                    return dict(tool="finish", args={"answer":"April 4", "missing_facts":[]})
                with Memory(lambda _: [1.0], lambda _: Summaries("long", "short")) as mem:
                    r = run("When?", tools, actor, FullHistory() if mode == "react" else mem,
                            Settings(8, glimpse_limit=0 if mode == "react" else 3), Utf8Counter(), 3)
                self.assertEqual(r["answer"], "April 4")

    def test_incomplete_finish_checks_only_once_and_keeps_honest_answer(self):
        calls = []
        def reread(args):
            calls.append(args)
            return "Page says nothing about it."
        tools = {"reread": Tool("reopens page", reread),
                 "visit": Tool("reads page", lambda _: '[{"read":true,"source_id":"S1"}]')}
        action = {"tool":"finish","args":{"answer":"Unknown", "source_id":"S1","missing_facts":["date"]}}
        actions = iter([{"tool":"visit","args":{}}, action, action, action])
        r = run("When?", tools, lambda _: next(actions), FullHistory(),
                Settings(8, glimpse_limit=0), Utf8Counter(), 4)
        self.assertEqual(r["answer"], "Unknown")
        self.assertEqual(calls, [{"source_id":"S1","goal":"date"}])
        self.assertEqual(r["steps"][1]["evidence_review"]["tool"], "reread")
        self.assertEqual(len(r["steps"]), 3)


if __name__ == "__main__":
    unittest.main()

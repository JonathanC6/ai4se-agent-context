import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from benchmarks.paper_pilot import CAP, FullHistory, episode
from pace.memory import Summaries
from benchmarks.webwalker_snapshot import site_tools, snapshot_digest
from pace import Builder, Settings, Turn
from pace.providers import Utf8Counter


class PaperPilotTests(unittest.TestCase):
    def test_react_retains_every_observation_to_step_cap(self):
        memory = FullHistory()
        for i in range(CAP - 1):
            memory.append(Turn("read", "visit", f"evidence-{i}", "visit"))
        context = Builder("system", "question", memory,
                          Settings(16, recent=CAP + 1, glimpse_limit=0), Utf8Counter()).build()
        self.assertEqual(len(context.selections), CAP - 1)
        self.assertTrue(all(s.shown.name == "FULL" and s.cosine is None for s in context.selections))
        self.assertIn("evidence-0", context.messages[-1]["content"])

    def test_episode_respects_step_and_budget_settings_and_records_summaries(self):
        row = {"question": "Q", "answer": "A", "root_url": "https://example.org/"}
        api = Mock(usage={}, last_input_tokens={})
        api.chat.return_value = {"tool": "unknown", "args": {}}
        api.summarize.return_value = Summaries("detailed", "brief")
        for budget, expected in [(128000, "step_limit"), (1, "budget_exceeded")]:
            with self.subTest(budget=budget), tempfile.TemporaryDirectory() as tmp:
                episode((1, 1, "pace"), {"horizon": 16, "max_steps": 1, "budget": budget}, [row],
                        None, lambda _: [1.0], Path(tmp), browser=lambda *_: {}, api_factory=lambda: api)
                record = json.loads((Path(tmp) / "rep-1/pace/row-1.json").read_text())
                self.assertEqual(record["status"], expected)
                if expected == "step_limit":
                    self.assertEqual(len(record["steps"]), 1)
                    self.assertEqual(record["history"][0]["summaries"]["brief"], "brief")

    def test_top_ten_snippets_and_legacy_top_eight(self):
        pages = [dict(url=f"https://example.org/{i}", title=f"Day {i}",
                      text=f"Opening schedule marker-{i}") for i in range(12)]
        snap = dict(pages=pages, sha256=snapshot_digest(pages))
        compact = site_tools(snap)["search"].call({"query":"schedule"})
        extended = site_tools(snap, result_limit=10, snippets=True)["search"].call({"query":"schedule"})
        self.assertEqual(len(compact.splitlines()), 8)
        self.assertNotIn("marker-", compact)
        self.assertEqual(len(extended.splitlines()), 10)
        self.assertTrue(all("marker-" in line for line in extended.splitlines()))

import unittest

from benchmarks.paper_pilot import CAP, FullHistory
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

import json
import unittest
from pathlib import Path
from unittest.mock import patch
from benchmarks.webwalker_frozen20 import FrozenBrowser


class FrozenSearchTest(unittest.TestCase):
    def setUp(self):
        self.page = "https://example.com/historic-answer.pdf"
        docs = [{"url": self.page, "keywords": ["meeting"]}]
        self.browser = FrozenBrowser("https://example.com/", None, 1, docs, "archive", Path("/unused"))

    def test_queries_return_identical_redacted_candidates(self):
        reply = self.browser.search({"query": "date"})
        self.assertEqual(reply, self.browser.search({"query": ["person", "conference"]}))
        self.assertEqual(json.loads(reply), [dict(id="doc-1", host="example.com", kind="pdf", keywords=["meeting"])])
        self.assertNotIn(self.page, reply)

    def test_visit_resolves_id_and_filters_leaked_links(self):
        links = [dict(url="https://another.com/program", title="program"),
                 dict(url="https://example.com/WebWalkerQA", title="dataset")]
        with patch.object(self.browser.backend, "visit", return_value=json.dumps([
                dict(url=self.page, read=True, links=links)])) as visit:
            result, = json.loads(self.browser.visit(dict(url="doc-1", goal="date")))
        self.assertEqual(visit.call_args.args[0]["url"], self.page)
        self.assertEqual(result["links"], links[:1])
        self.assertFalse(json.loads(self.browser.visit(dict(url=links[1]["url"], goal="answer")))[0]["read"])

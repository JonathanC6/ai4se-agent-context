import json
import unittest
from unittest.mock import patch
from benchmarks.google_you import PaperBrowser
from benchmarks.webwalker_tools20 import measurements


class ToolComparisonTests(unittest.TestCase):
    def setUp(self):
        self.browser = PaperBrowser(None, ("dummy-search", "dummy-reader"))

    @patch("benchmarks.google_you.post")
    def test_search_routes_by_query_and_caps_results(self, post):
        post.return_value = {"organic": [dict(title="x", link="https://example.org", snippet="e")] * 12}
        hits = json.loads(self.browser.search({"query": ["会议日期", "conference date"]}))
        self.assertEqual([len(h["results"]) for h in hits], [10, 10])
        self.assertEqual({c.args[2]["gl"] for c in post.call_args_list}, {"us", "cn"})

    @patch("benchmarks.google_you.extract_page", return_value="short evidence")
    @patch("benchmarks.google_you.post")
    def test_only_received_markdown_counts(self, post, extract):
        urls = ["https://www.example.org/a/", "https://example.org/b"]
        post.return_value = [{"url": urls[0], "markdown": "x" * 30000}]
        observation = self.browser.visit({"url": urls, "goal": ["date", "name"]})
        extract.assert_called_once()
        self.assertEqual(extract.call_args.args[-2:], (0, 24000))
        row = {"info": {"source_website": ["http://example.org/a#tag", urls[1]]}}
        record = {"history": [{"kind":"visit", "observation": observation}], "grade": {"correct": False}}
        scores = measurements(record, row, True)
        self.assertEqual((scores["matched"], scores["references"], scores["all_hit"]), (1, 2, False))

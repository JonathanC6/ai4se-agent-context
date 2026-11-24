import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarks.webwalker_live import Browser, Links, LEGACY_BROWSER, terms
from benchmarks.webwalker_full import report
from pace.records import write_result


class FullSplitTests(unittest.TestCase):
    def test_only_discovered_links_can_be_visited(self):
        root = "https://example.org/"
        url = root + "news"
        page = {"text": "消息", "links": {url: "学院活动新闻"}}
        browser = Browser(root, None, {"example.org"})
        with patch("benchmarks.webwalker_live.read_page", return_value=page) as fetch:
            self.assertIn(url, browser.search({"query":"活动"}).splitlines()[0])
            with self.assertRaises(ValueError):
                browser.load("https://example.org/undiscovered")
            self.assertEqual(fetch.call_count, 1)
        self.assertIn("活动", terms("重大活动"))

    def test_search_excludes_zero_score_but_keeps_homepage_available(self):
        root = "https://example.org/"
        page = {"text": "Home", "links": {root + "news": "Faculty news", root + "agenda": "Talks"}}
        with patch("benchmarks.webwalker_live.read_page", return_value=page):
            browser = Browser(root, None, {"example.org"})
            self.assertEqual(browser.search({"query": "faculty"}), "Faculty news | " + root + "news")
            self.assertIn("No matching", browser.search({"query": "deadline"}))
            legacy = Browser(root, None, {"example.org"}, LEGACY_BROWSER)
            self.assertIn(root + "news", legacy.search({"query": "deadline"}))

    def test_empty_main_falls_back_to_visible_text(self):
        parser = Links()
        parser.feed('<main>  </main><nav>Ignore</nav><section>Deadline: March 14</section>')
        self.assertEqual(parser.page("https://example.org/")["text"], "Deadline: March 14")
        self.assertEqual(parser.page("https://example.org/", fallback_empty=False)["text"], "")

    def test_nested_anchor_text(self):
        html = Links()
        html.feed('<nav><a href="/a"><strong>Paper</strong> deadline</a></nav>')
        self.assertEqual(html.labels["/a"], "Paper deadline")

    def test_api_failure_does_not_shrink_denominator(self):
        row = {"info":{"type":"single_source"}}
        with tempfile.TemporaryDirectory() as tmp, patch("benchmarks.webwalker_full.OUT", Path(tmp)):
            base = Path(tmp) / "rep-1/pace"
            result = {"status":"finished", "steps":[{}], "grade":{"correct":True}, "usage":{},
                      "history":[{"kind":"visit", "observation":"https://example.org/ chars 0:7/7\n{}\nDiscovered links:\n"}]}
            write_result(base / "row-1.json", result)
            write_result(base / "row-2.json", {"answer":"waiting for judge"})
            cfg = {"arms":["pace"], "repeats":1}
            partial, = report([row,row], cfg)
            self.assertIsNone(partial["accuracy"])
            self.assertEqual(partial["missing"],1)
            result.update(grade={"correct":False}, history=[{"kind":"visit", "observation":"No page text.\nDiscovered links:\nhttps://example.org/"}])
            write_result(base / "row-2.json", result)
            complete, = report([row,row], cfg)
            self.assertEqual(complete["accuracy"], 0.5)
            self.assertEqual(complete["counts"]["no_successful_visit"],1)

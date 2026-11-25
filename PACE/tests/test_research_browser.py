import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from benchmarks.research_browser import ResearchBrowser, WINDOW
from benchmarks.webwalker_live import received_page_text
from pace.providers import ProviderError


ROOT = "https://example.org/"


class ResearchBrowserTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        for key, val in [("CACHE", self.base / "cache"), ("optional_credentials", lambda: (None, None))]:
            p = patch("benchmarks.research_browser." + key, val)
            p.start()
            self.addCleanup(p.stop)
        for p in [patch("benchmarks.research_browser.public_url"),
                  patch("benchmarks.archive_reader.extract_page", return_value="fact")]:
            p.start()
            self.addCleanup(p.stop)

    def browser(self, name):
        path = self.base / name
        path.mkdir()
        return ResearchBrowser(ROOT, None, 1, path)

    def test_pages_are_frozen_across_arms_and_reread_is_per_episode(self):
        first, second = self.browser("arm-one"), self.browser("arm-two")
        text = "# Site\n[Deadline](/agenda) before March 1"
        with patch.object(first.backend.you, "fetch_pages", return_value=[dict(url=ROOT, markdown=text)]) as download:
            first_page, = json.loads(first.visit(dict(url=ROOT, goal="deadline")))
            self.assertEqual(download.call_count, 1)
        self.assertFalse(second.evidence.sources)
        with patch.object(second.backend.you, "fetch_pages", side_effect=AssertionError("download repeated")):
            second_page, = json.loads(second.visit(dict(url=ROOT, goal="deadline")))
        self.assertEqual(first_page["text_sha256"], second_page["text_sha256"])
        self.assertEqual(second_page["links"], [{"url": ROOT + "agenda", "title": "Deadline"}])
        self.assertTrue(received_page_text(dict(kind="visit", observation=json.dumps([first_page]))))

    def test_read_failed_you_with_direct_pdf_and_locate_late_passage(self):
        b = self.browser("arm")
        text = ("opening " * WINDOW) + "sedimentation"
        with patch.object(b.backend.you, "fetch_pages", side_effect=ProviderError("HTTP 429")), \
             patch("benchmarks.research_browser.document", return_value=(ROOT, "pdf", text, {})):
            page, = json.loads(b.visit(dict(url=ROOT, goal="sedimentation")))
            self.assertEqual(page["format"], "pdf")
            self.assertGreater(page["window"][0], 0)
            self.assertIn("sedimentation", text[slice(*page["window"])])
            data = list(map(json.loads, (b.backend.output / "reader-1.jsonl").read_text().splitlines()))
            doc = next(info for kind, info in data if kind == "document")
            self.assertEqual(doc["backend"], "direct")
            self.assertEqual(doc["fallback_reason"], "HTTP 429")

    def test_failed_visit_is_replayed_and_never_grants_a_source(self):
        first, second = self.browser("first"), self.browser("second")
        with patch.object(first.backend, "fetch_document", side_effect=ValueError("missing snapshot")):
            failed, = json.loads(first.visit(dict(url=ROOT, goal="date", as_of="2023-04-01")))
        with patch.object(second.backend, "fetch_document", side_effect=AssertionError("retried frozen URL")):
            repeated, = json.loads(second.visit(dict(url=ROOT, goal="date", as_of="2023-04-01")))
        self.assertEqual(failed, repeated)
        self.assertFalse(repeated["read"])
        self.assertFalse(second.evidence.sources)

    def test_serper_keeps_ranking_filters_mirrors_and_is_shared(self):
        rows = [dict(url=ROOT + tail, title=title, snippet="snippet") for tail, title in
                [("later", "First result"), ("WebWalkerQA", "Dataset"), ("first", "Second result")]]
        with patch("benchmarks.research_browser.optional_credentials", return_value=("test-key", None)):
            first, second = self.browser("google1"), self.browser("google2")
        with patch.object(first.google, "search_one", return_value={"results": rows}):
            results = json.loads(first.search({"query": "conference dates"}))[0]["results"]
        with patch.object(second.google, "search_one", side_effect=AssertionError("repeated Google query")):
            again = json.loads(second.search({"query": "conference dates"}))[0]["results"]
        self.assertEqual(results, [rows[0], rows[2]])
        self.assertEqual(results, again)
        self.assertTrue({ROOT + "later", ROOT + "first"}.issubset(second.allowed))

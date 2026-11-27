import unittest
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
import json

from benchmarks.usage_meter import add_measurement
from benchmarks.webwalker_full import FullRunAPI
from pace.providers import ProviderError
from pace.providers.encoding import LabhuanCounter, VisibleWindowCounter


class FakeTokenizer:
    def encode(self, value, add_special_tokens):
        return SimpleNamespace(ids=value.split())


class InputBudgetTests(unittest.TestCase):
    def test_visible_window_is_independent_of_gateway_usage(self):
        counter = VisibleWindowCounter(FakeTokenizer(), scale=1, framing=100)
        first = [{"content": "one two"}]
        counter.observe(first, 72000)
        self.assertEqual(counter.messages(first), 102)

    def test_only_prior_usage_corrects_next_prompt(self):
        counter = LabhuanCounter(FakeTokenizer(), scale=1, framing=100)
        first = [{"content": "one two"}]
        self.assertEqual(counter.messages(first), 102)
        counter.observe(first, 132)
        self.assertEqual(counter.messages([{"content": "one two three"}]), 133)
        counter.observe(first, 92)
        self.assertEqual(counter.messages(first), 92)
        self.assertEqual(counter.text("一 二 三"), 3)

    def test_missing_provider_usage_is_not_scored(self):
        with self.assertRaises(ProviderError):
            LabhuanCounter(FakeTokenizer()).observe([], None)

    def test_summary_ledger_keeps_gateway_and_visible_counts_separate(self):
        usage = {"prompt_tokens":9000, "completion_tokens":10, "total_tokens":9010,
                 "prompt_tokens_details":{"cached_tokens":8900,"cached_creation_tokens":80}}
        response = {"id":"example", "usage":usage,
                    "choices":[{"message":{"content":"two words"},"finish_reason":"stop"}]}
        body = {"model":"test", "messages":[{"role":"user", "content":"three short words"}]}
        meter = VisibleWindowCounter(FakeTokenizer(), scale=1, framing=100)
        with TemporaryDirectory() as folder:
            api = FullRunAPI("https://example.org", "unused")
            api.job, api.output = (1,1,"pace"), Path(folder)
            with patch.object(api, "request_json", return_value=response), patch(
                    "benchmarks.webwalker_full.local_meter", return_value=meter):
                api.post("/chat/completions", body, "summary")
            entry = json.loads((api.output/"usage.jsonl").read_text())
        self.assertEqual((entry["input_text_subwords"],entry["visible_input_estimate"],
                          entry["output_text_subwords"]), (3,103,2))
        self.assertEqual(entry["total_tokens"], 9010)
        self.assertEqual(entry["prompt_cache_details"]["cached_tokens"], 8900)
        self.assertTrue(entry["gateway_total_matches_parts"])
        self.assertNotIn("three short words", str(entry))
        totals = {}
        add_measurement(totals, entry)
        add_measurement(totals, {"role":"summary", "total_tokens":123})
        self.assertEqual(totals["responses"], 2)
        self.assertEqual(totals["visible_input_estimate_responses"], 1)

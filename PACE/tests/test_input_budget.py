import unittest
from types import SimpleNamespace

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

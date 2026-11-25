import json
import unittest

from benchmarks.actor_budget import BudgetedActor
from pace.agent import Tool, run
from pace.context import BudgetExceeded
from pace.memory import Memory, Summaries
from pace.policy import Settings
from pace.providers import ReplyFormatError, Utf8Counter
from test_actor_budget import MockAPI


class ReviewedActorTests(unittest.TestCase):
    def test_only_first_double_format_failure_uses_question_search(self):
        api = MockAPI([(50, '{}'), (55, 'invalid'), (60, 'invalid'), (65, 'invalid')])
        actor = BudgetedActor(api, "model", Utf8Counter(), 6000, seed_query="question?")
        messages = [{"role": "system", "content": "JSON"}, {"role": "user", "content": "question?"}]
        first = actor(messages)
        self.assertEqual((first["tool"], first["args"]), ("search", {"query": "question?"}))
        self.assertEqual(first["origin"], "first_step_fallback")
        with self.assertRaises(ReplyFormatError):
            actor(messages)
        self.assertEqual(len(api.calls), 4)
        self.assertTrue(all(body["response_format"] == {"type": "json_object"} for _, body in api.calls))

    def test_valid_action_and_budget_stop_stay_in_effect(self):
        prompt = [{"role": "system", "content": "JSON"}, {"role": "user", "content": "question?"}]
        api = MockAPI([(70, '{"tool":"finish","args":{"answer":"original"}}')])
        actor = BudgetedActor(api, "model", Utf8Counter(), 6000, seed_query="question?")
        self.assertEqual(actor(prompt), {"tool": "finish", "args": {"answer": "original"}})
        with self.assertRaises(BudgetExceeded):
            BudgetedActor(api, "model", Utf8Counter(), 1, seed_query="question?")(prompt)
        self.assertEqual(len(api.calls), 1)

    def test_compressed_successful_visit_reopened_once_before_finish(self):
        visit = json.dumps([{"read": True, "source_id": "S1", "extraction": "opens March 14"}])
        actions = iter([{"tool": "visit", "args": {}}, {"tool": "search", "args": {}},
                        {"tool": "finish", "args": {"answer": "March 13"}},
                        {"tool": "finish", "args": {"answer": "March 14"}}])
        tools = {"visit": Tool("visit", lambda _: visit), "search": Tool("search", lambda _: "[]")}
        settings = Settings(20, recent=1, thresholds=(2, 3, 4))
        with Memory(lambda _: [1], lambda _: Summaries("a date", "date")) as memory:
            record = run("When?", tools, lambda _: next(actions), memory, settings, Utf8Counter(), 4,
                         coverage_check=lambda _: {"target": "", "goal": ""}, verify_compressed=True)
        self.assertEqual(record["answer"], "March 14")
        self.assertEqual(record["steps"][2]["evidence_review"]["args"], {"ids": [1]})
        self.assertEqual(record["steps"][2]["coverage"]["status"], "verify_compressed")
        self.assertEqual(record["glimpse_calls"], 1)

    def test_finish_on_last_turn_does_not_trigger_a_review(self):
        actions = iter([{"tool": "visit", "args": {}}, {"tool": "search", "args": {}},
                        {"tool": "finish", "args": {"answer": "March 14"}}])
        visit = json.dumps([{"read": True, "source_id": "S1", "extraction": "opens March 14"}])
        tools = {"visit": Tool("visit", lambda _: visit), "search": Tool("search", lambda _: "[]")}
        with Memory(lambda _: [1], lambda _: Summaries("a date", "date")) as memory:
            record = run("When?", tools, lambda _: next(actions), memory, Settings(20, recent=1),
                         Utf8Counter(), 3, coverage_check=lambda _: self.fail("last step"), verify_compressed=True)
        self.assertEqual(record["answer"], "March 14")
        self.assertEqual(record["glimpse_calls"], 0)

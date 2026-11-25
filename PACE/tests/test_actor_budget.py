import unittest

from benchmarks.actor_budget import BudgetedActor
from benchmarks.paper_pilot import FullHistory
from benchmarks.research_budget_audit import audit_episode, match_legacy, v2_outcome
from pace.agent import run
from pace.context import BudgetExceeded
from pace.policy import Settings
from pace.providers import API
from pace.providers.encoding import Utf8Counter


class MockAPI(API):
    def __init__(self, replies):
        super().__init__("https://example.invalid/v1", "")
        self.replies = iter(replies)
        self.calls = []

    def post(self, path, body, purpose):
        actual, content = next(self.replies)
        self.calls.append((self.actor_log.copy(), body))
        self.last_input_tokens[purpose] = actual
        return {"usage": {"prompt_tokens": actual}, "choices": [{"message": {"content": content}}]}


def event(index, actual):
    return dict(ledger_line=index, prompt_tokens=actual, completion_tokens=1, total_tokens=actual + 1)


class StrictBudgetTests(unittest.TestCase):
    prompt = [{"role": "system", "content": "json"}, {"role": "user", "content": "q"}]

    def test_observe_gateway_retries_and_executes_over_reference_but_keeps_local_cap(self):
        api = MockAPI([(200000, "malformed"), (215000, '{"tool":"finish","args":{"answer":"done"}}')])
        counter = Utf8Counter()
        actor = BudgetedActor(api, "mock", counter, 4000, 80000, enforce_provider_budget=False)
        record = run("q", {}, actor, FullHistory(), Settings(20, budget=4000), counter, 1,
                     lambda: api.last_input_tokens["actor"], provider_input_budget=80000,
                     enforce_provider_budget=False)
        self.assertEqual(record["answer"], "done")
        self.assertEqual(record["steps"][0]["input_tokens_actual"], 215000)
        self.assertEqual([log["format_attempt"] for log, _ in api.calls], [1, 2])
        tiny = BudgetedActor(api, "mock", counter, 1, 80000, enforce_provider_budget=False)
        with self.assertRaises(BudgetExceeded):
            tiny(self.prompt)
        self.assertEqual(len(api.calls), 2)

    def test_local_visible_and_provider_budgets_are_enforced_separately(self):
        api = MockAPI([(4000, '{"tool":"finish"}'), (4001, "invalid JSON")])
        actor = BudgetedActor(api, "mock", Utf8Counter(), 1000, provider_input_budget=4000)
        self.assertEqual(actor(self.prompt), {"tool": "finish"})
        self.assertEqual(actor(self.prompt), {})
        self.assertEqual(len(api.calls), 2)

    def test_over_budget_malformed_response_stops_before_retry(self):
        api = MockAPI([(2000, "bad")])
        actor = BudgetedActor(api, "mock", Utf8Counter(), 1000)
        self.assertEqual(actor(self.prompt), {})
        self.assertEqual(len(api.calls), 1)

    def test_over_budget_results_in_a_rejected_step_and_no_observation(self):
        api = MockAPI([(9000, "bad")])
        counter = Utf8Counter()
        actor = BudgetedActor(api, "mock", counter, 1000)
        memory = FullHistory()
        record = run("test", {}, actor, memory, Settings(10, budget=1000), counter, 2,
                     lambda: api.last_input_tokens["actor"], last_actor_messages=lambda: actor.last_messages)
        self.assertEqual(record["status"], "budget_exceeded")
        self.assertIsNone(record["answer"])
        self.assertEqual(record["steps"][0]["action"], {})
        self.assertEqual(record["steps"][0]["input_tokens_actual"], 9000)
        self.assertFalse(memory.chunks)

    def test_over_budget_retry_preflight_is_never_sent(self):
        api = MockAPI([(70, "bad")])
        actor = BudgetedActor(api, "mock", Utf8Counter(), 72)
        with self.assertRaisesRegex(BudgetExceeded, "format retry"):
            actor(self.prompt)
        self.assertEqual(len(api.calls), 1)

    def test_log_shows_decision_and_retry(self):
        api = MockAPI([(70, "bad"), (81, '{"tool":"finish"}'), (90, '{}')])
        actor = BudgetedActor(api, "mock", Utf8Counter(), 1000)
        self.assertEqual(actor(self.prompt), {"tool": "finish"})
        self.assertNotEqual(actor.last_messages, self.prompt)
        actor(self.prompt)
        self.assertEqual([(log["decision_step"], log["format_attempt"]) for log, _ in api.calls],
                         [(1, 1), (1, 2), (2, 1)])

    def test_legacy_suffix_and_failed_format_response_change_strict_score(self):
        events = [event(4, 4), event(6, 70), event(8, 171), event(10, 87)]
        record = dict(status="finished", grade={"correct": True}, steps=[
            {"input_tokens_actual": 70}, {"input_tokens_actual": 87}],
            usage={"actor": dict(requests=3, prompt_tokens=328, completion_tokens=3, total_tokens=331)})
        case = audit_episode(record, events, 100)
        self.assertEqual(case["discarded_run_actor_tokens"], 5)
        self.assertFalse(case["strict_correct"])
        self.assertEqual((case["first_over_budget"]["step"], case["first_over_budget"]["ledger_line"]), (2, 8))
        self.assertTrue(case["first_over_budget"]["discarded_for_format"])
        self.assertEqual(case["attempts"][-1]["format_attempt"], 2)

    def test_legacy_non_unique_assignment_is_unscorable(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            match_legacy([{"input_tokens_actual": 60}] * 2, [event(i, 60) for i in range(3)])

    def test_explicit_ids_match_even_when_counts_are_identical(self):
        events = [dict(event(i, 50), episode_id="run", decision_step=step, format_attempt=a,
                       input_tokens_estimate=45) for i, (step, a) in enumerate([(1, 1), (1, 2), (2, 1)], 1)]
        record = dict(status="finished", grade={"correct": True}, actor_episode_id="run", steps=[
            dict(input_tokens_actual=50, input_tokens_estimate=45) for _ in range(2)],
            usage={"actor": dict(requests=3, prompt_tokens=150, completion_tokens=3, total_tokens=153)})
        self.assertTrue(audit_episode(record, events, 55)["strict_correct"])

    def test_replay_requires_identical_post_retry_visibility(self):
        record = dict(grade={"correct": True}, status="finished", history=[{}], steps=[
            dict(step=1, input_tokens_estimate=70, chunks=[]),
            dict(step=2, input_tokens_estimate=70, chunks=[
                dict(selected="FULL", shown="BRIEF", summaries="ready")])])
        attempts = [dict(step=s, format_attempt=a, prompt_tokens=65) for s, a in [(1, 1), (1, 2), (2, 1)]]
        self.assertFalse(v2_outcome(record, attempts, 100, 20)["v2_equivalent"])
        record["steps"][1]["chunks"][0]["shown"] = "FULL"
        self.assertTrue(v2_outcome(record, attempts, 100, 20)["v2_correct"])
        replay = v2_outcome(record, attempts, 85, 20)
        self.assertEqual((replay["v2_stop_reason"], replay["v2_steps"]), ("retry_preflight", 0))

    def test_preflight_after_retry_near_boundary_requires_new_run(self):
        record = dict(grade={"correct": False}, status="budget_exceeded", history=[{}],
                      error="required context need 110 tokens (budget 100)",
                      steps=[dict(step=1, input_tokens_estimate=70, chunks=[])])
        attempts = [dict(step=1, format_attempt=a, prompt_tokens=68) for a in [1, 2]]
        self.assertFalse(v2_outcome(record, attempts, 100, 20)["v2_equivalent"])
        record["error"] = "required context need 125 tokens (budget 100)"
        self.assertTrue(v2_outcome(record, attempts, 100, 20)["v2_equivalent"])

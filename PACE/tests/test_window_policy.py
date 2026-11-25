import math
import unittest

from pace import Builder, Memory, Settings, Summaries, Turn, run
from pace.agent import Tool
from pace.policy import Level
from pace.providers import Utf8Counter


class WindowPolicyTests(unittest.TestCase):
    def setUp(self):
        self.mem = Memory(lambda _: [1.], lambda _: Summaries("detail", "brief"))
        self.addCleanup(self.mem.pool.shutdown)
        self.counter = Utf8Counter()

    def append(self, body):
        self.mem.append(Turn("", "read", body)).summaries.result()

    def test_gate_then_unweighted_first_and_current_window_pressure(self):
        for _ in range(4):
            self.append("content" * 20)
        all_full = Builder("s", "q", self.mem, Settings(1, recent=99), self.counter).build()
        budget = math.ceil(all_full.tokens / .85)
        def settings(ratio):
            return Settings(1, budget=budget, pressure_mode="window", compression_start_ratio=ratio)
        under = Builder("s", "q", self.mem, settings(.90), self.counter).build()
        self.assertEqual(under.window["phase"], "full_history")
        self.assertTrue(all(row.shown == Level.FULL and row.summary_state == "ready" for row in under.selections))
        b = Builder("s", "q", self.mem, settings(.80), self.counter)
        first = b.build()
        self.assertEqual((first.window["phase"], first.pressure), ("first_multilevel", 0.))
        self.assertEqual(first.boundaries, b.settings.thresholds)
        self.assertTrue(any(row.shown != Level.FULL for row in first.selections))
        self.append("new observation")
        next_step = b.build()
        expected = b.messages_from_blocks([row.block(row.shown) for row in first.selections] +
                                          [next_step.selections[-1].block(Level.FULL)])
        self.assertEqual(next_step.window["current_input_estimate"], self.counter.messages(expected))
        self.assertLess(next_step.window["current_input_estimate"], next_step.window["full_input_estimate"])
        self.assertEqual(next_step.window["phase"], "multilevel")
        self.assertEqual(next_step.pressure, self.counter.messages(expected) / budget)
        self.assertEqual(next_step.window["organized_input_estimate"], next_step.tokens)

    def test_gate_can_latch_before_any_chunk_is_eligible(self):
        self.append("a" * 400)
        b = Builder("s", "q", self.mem, Settings(1, budget=750, recent=1, pressure_mode="window",
                                                  compression_start_ratio=.5), self.counter)
        waiting = b.build()
        self.assertEqual(waiting.window["phase"], "awaiting_old_chunk")
        self.assertIsNone(waiting.window["first_organization_step"])
        self.append("b")
        first = b.build()
        self.assertEqual(first.window["activation_step"], waiting.step)
        self.assertEqual(first.window["first_organization_step"], first.step)
        self.assertEqual(first.pressure, 0)

    def test_window_only_ignores_step_and_provider_counts(self):
        for _ in range(4):
            self.append("fact " * 10)
        cfg = Settings(1, budget=2000, pressure_mode="window")
        b = Builder("s", "q", self.mem, cfg, self.counter)
        b.previous_tokens = 80000
        ctx = b.build()
        self.assertEqual(ctx.pressure, ctx.window["full_input_estimate"] / cfg.budget)
        self.assertLess(ctx.pressure, 1)
        for bad in (0, -.1, 1.1, float("nan")):
            with self.assertRaises(ValueError):
                Settings(1, compression_start_ratio=bad)

    def test_visible_and_provider_limits_are_enforced_separately(self):
        actions = iter([{"tool": "read", "args": {}}, {"tool": "finish", "args": {"answer": "done"}}])
        with Memory(lambda _: [1.], lambda _: Summaries("detail", "brief")) as m:
            rec = run("goal", {"read": Tool("read", lambda _: "fact")}, lambda _: next(actions), m,
                      Settings(100, budget=4000), self.counter, 2, lambda: 6000, provider_input_budget=8000)
        self.assertEqual(rec["status"], "finished")
        self.assertAlmostEqual(rec["steps"][1]["pressure"], rec["steps"][0]["input_tokens_estimate"] / 4000)
        stop = run("goal", {}, lambda _: {"tool": "finish", "args": {"answer": "unused"}}, self.mem,
                   Settings(100, budget=4000), self.counter, 1, lambda: 8001, provider_input_budget=8000)
        self.assertEqual(stop["status"], "budget_exceeded")
        self.assertIsNone(stop["answer"])
        local = run("goal", {}, lambda _: self.fail("local overflow must block the request"), self.mem,
                    Settings(10, budget=10), self.counter, 1, provider_input_budget=8000)
        self.assertGreater(local["budget_stop_window"]["full_input_estimate"], 10)

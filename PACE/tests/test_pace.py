import json
import math
import threading
import unittest
from pathlib import Path

from pace import BudgetExceeded, Builder, Memory, Settings, Summaries, Turn, run
from pace.__main__ import demo_actor
from pace.agent import snapshot_tools
from pace.policy import Level, p95, relative_weights
from pace.providers import Utf8Counter, demo_encode


def summaries(_):
    return Summaries("A longer summary.", "A note.")


class PaperPolicyTests(unittest.TestCase):
    def test_all_four_representations_in_one_context(self):
        target = [.2, .6, 1.0, 2.2]  # Mean one, so these are recovered by Eq. (5).
        def encode(text):
            if text.startswith("goal"):
                return [1, 0]
            idx = int(text.rsplit(" ", 1)[1])
            x = .3 * math.log(target[idx]) if idx < 4 else 0
            return [x, math.sqrt(1 - x*x)]
        with Memory(encode, summaries) as mem:
            for i in range(6):
                mem.append(Turn("", "read", str(i))).summaries.result()
            ctx = Builder("sys", "goal", mem, Settings(1000), Utf8Counter()).build()
            self.assertEqual([row.shown for row in ctx.selections],
                             [*Level, Level.FULL, Level.FULL])
            for row, w in zip(ctx.selections, target):
                self.assertAlmostEqual(row.weight, w)

    def test_weights_and_strict_boundaries(self):
        cfg = Settings(100)
        self.assertEqual(relative_weights([], .3), [])
        self.assertEqual(relative_weights([.5, .5, .5], .3), [1, 1, 1])
        a, b = relative_weights([1, 0], .3)
        self.assertAlmostEqual(a + b, 2)
        self.assertGreater(a, b)
        bounds = cfg.boundaries(1)
        self.assertEqual([cfg.level(x, bounds) for x in bounds],
                         [Level.PLACEHOLDER, Level.BRIEF, Level.DETAILED])
        self.assertEqual(cfg.level(bounds[-1]+1e-6, bounds), Level.FULL)
        self.assertEqual(cfg.pressure(999, 0), 1)
        self.assertEqual(p95(list(range(1, 101))), 95)

    def test_cached_full_keys_query_recent_only_and_pressure(self):
        calls = []
        def encode(text):
            calls.append(text)
            return [2.0, 1.0]
        with Memory(encode, summaries) as mem:
            cfg = Settings(80, budget=4000)
            builder = Builder("sys", "goal", mem, cfg, Utf8Counter())
            first = builder.build()
            self.assertEqual(first.pressure, max(1/80, first.tokens/4000))
            for i in range(4):
                mem.append(Turn("t", "read", f"evidence-{i}")).summaries.result()
            c = builder.build()
            self.assertEqual(len(calls), 5)
            self.assertEqual(calls[-1], "\n\n".join(["goal"]+[x.full for x in mem.chunks[-2:]]))
            self.assertEqual([s.chunk.id for s in c.selections], [1, 2, 3, 4])
            self.assertEqual([s.weight for s in c.selections], [1, 1, None, None])
            self.assertTrue(all(s.shown == Level.FULL for s in c.selections[-2:]))
            builder.build()
            self.assertEqual(len(calls), 6)

    def test_pending_summary_falls_back_without_blocking(self):
        finish = threading.Event()
        def blocked(_):
            finish.wait(5)
            return summaries("")
        with Memory(demo_encode, blocked) as mem:
            try:
                for i in range(3):
                    mem.append(Turn("", "read", "many words " * 20))
                b = Builder("sys", "goal", mem, Settings(50), Utf8Counter())
                row = b.build().selections[0]
                self.assertEqual((row.requested, row.shown, row.summary_state),
                                 (Level.DETAILED, Level.FULL, "pending"))
                b = Builder("sys", "goal", mem, Settings(50, budget=730), Utf8Counter())
                c = b.build()
                self.assertEqual(c.selections[0].shown, Level.PLACEHOLDER)
                self.assertLessEqual(c.tokens, 730)
            finally:
                finish.set()

    def test_failed_summary_and_impossible_budget(self):
        def broken(_):
            raise ValueError("summary failed")
        with Memory(demo_encode, broken) as mem:
            c = mem.append(Turn("test", "read", "X" * 500))
            self.assertIsInstance(c.summaries.exception(), ValueError)
            self.assertEqual(c.summary_snapshot()[1], "failed/ValueError")
            b = Builder("sys", "goal", mem, Settings(50, budget=200), Utf8Counter())
            with self.assertRaises(BudgetExceeded):
                b.build()
            self.assertIn("X" * 500, mem.glimpse([1]))

    def test_glimpse_identity_limits_and_next_input(self):
        with Memory(demo_encode, summaries) as mem:
            mem.append(Turn("inspect", "read", "original"))
            for bad in ([], [0], [2], [True], [1,1], [1,2,3,4], "C1"):
                with self.assertRaises(ValueError):
                    mem.glimpse(bad)
            calls = []
            def actor(messages):
                calls.append(messages)
                return ({"tool":"glimpse", "args":{"ids":[1]}} if len(calls)==1 else
                        {"tool":"finish", "args":{"answer":"done"}})
            r = run("goal", {}, actor, mem, Settings(10), Utf8Counter(), 2)
            self.assertEqual(r["glimpse_calls"], 1)
            self.assertIn("Observation: [C1]\n" + mem.chunks[0].full, calls[-1][1]["content"])
            self.assertEqual(r["steps"][-1]["input_tokens_estimate"], Utf8Counter().messages(calls[-1]))

    def test_real_usage_controls_next_pressure_and_reference_is_held_out(self):
        task = json.loads((Path(__file__).resolve().parents[1]/"examples/workshop.json").read_text())
        actor = demo_actor()
        def checked(messages):
            self.assertNotIn(task["reference"], messages[1]["content"])
            return actor(messages)
        with Memory(demo_encode, summaries) as mem:
            result = run(task["question"], snapshot_tools(task["pages"]), checked, mem,
                         Settings(100, budget=10000), Utf8Counter(), 10, lambda: 7500)
            self.assertEqual(result["steps"][1]["pressure"], .75)
            self.assertEqual(result["answer"], task["reference"])
            self.assertEqual(len(result["steps"]), 6)


if __name__ == "__main__":
    unittest.main()

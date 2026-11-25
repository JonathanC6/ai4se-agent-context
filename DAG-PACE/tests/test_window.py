import math
import unittest

from dag_pace.strategy import DependencyStrategy
from pace import Builder, Memory, Settings, Summaries, Turn
from pace.policy import Level
from pace.providers import Utf8Counter


class DagWindowTests(unittest.TestCase):
    def test_replaced_blocks_do_not_count_and_gate_stays_open(self):
        with Memory(lambda _: [1.], lambda _: Summaries("detail", "brief")) as m:
            for _ in range(6):
                m.append(Turn("", "read", "evidence " * 20)).summaries.result()
            counter = Utf8Counter()
            full = Builder("s", "q", m, Settings(16, recent=99), counter).build()
            strategy = DependencyStrategy(top_k=0)
            b = Builder("s", "q", m, Settings(16, budget=math.ceil(full.tokens / .85),
                        pressure_mode="window", compression_start_ratio=.8), counter, strategy)
            first = b.build()
            self.assertEqual(first.window["phase"], "first_multilevel")
            self.assertNotEqual(first.selections[0].shown, Level.FULL)
            m.append(Turn("", "visit", "new")).summaries.result()
            strategy.record(7, {"critical_anchor_ids": [1], "supersedes_chunk_ids": [2, 3, 4]}, set(range(1, 7)))
            after = b.build()
            self.assertEqual(after.window["phase"], "multilevel")
            self.assertLess(after.window["full_input_estimate"], .8 * b.settings.budget)
            self.assertEqual([s.chunk.id for s in after.selections], [1, 5, 6, 7])
            self.assertEqual(after.selections[0].shown, Level.FULL)
            self.assertEqual(after.window["current_input_estimate"], after.window["full_input_estimate"])

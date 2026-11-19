import unittest

from dag_pace.strategy import DependencyStrategy
from pace import Builder, Memory, Settings, Summaries, Turn
from pace.context import BudgetExceeded
from pace.policy import Level
from pace.providers import Utf8Counter


class DependencyTests(unittest.TestCase):
    def test_validation_and_version_chain(self):
        strategy = DependencyStrategy()
        strategy.record(1, {}, set())
        meta = strategy.record(2, {"used_chunk_ids": [1, 2, 8, True], "critical_anchor_ids": [1]}, {1})
        self.assertEqual(meta["parents"], [1])
        self.assertEqual(strategy.anchors, {1})
        strategy.record(3, {"supersedes_chunk_ids": [1, 2]}, {1, 2})
        strategy.record(4, {"supersedes_chunk_ids": [2]}, {2, 3})
        self.assertEqual(strategy.resolve(1), 3)
        self.assertFalse(strategy.active(2))
        self.assertFalse(strategy.anchors)

    def test_two_hops_only_and_anchor_budget(self):
        with Memory(lambda _: [1.0], lambda _: Summaries("detail", "brief")) as memory:
            strategy = DependencyStrategy(top_k=1)
            for i in range(1, 9):
                memory.append(Turn("", "visit", "content" * 90)).summaries.result()
                strategy.record(i, {}, set(range(1, i)))
            # 一个种子汇合两支前驱，共同祖先只升一级。
            strategy.parents.update({6: {4, 5}, 4: {3}, 5: {3}})
            rows = Builder("s", "q", memory, Settings(100), Utf8Counter()).build().selections
            rows[5].weight = 2.0
            base = rows[2].requested
            trace = strategy.adjust(rows, 6)
            self.assertEqual(trace["ancestors"], [3, 4, 5])
            self.assertEqual(rows[2].requested, Level(min(3, base + 1)))
            strategy.anchors.add(2)
            builder = Builder("s", "q", memory, Settings(100, budget=1650), Utf8Counter(), strategy)
            with self.assertRaises(BudgetExceeded):
                builder.build()

    def test_invalid_or_failed_replacement(self):
        strategy = DependencyStrategy()
        strategy.record(1, {}, set())
        strategy.record(2, {}, {1}, failed=True)
        strategy.record(3, {"supersedes_chunk_ids": [1]}, {1, 2})
        self.assertTrue(strategy.active(1))


class AblationFieldsTests(unittest.TestCase):
    def test_dag_and_anchor_disable_later_modules_even_if_model_emits_extra_fields(self):
        reply = {"used_chunk_ids": [1], "critical_anchor_ids": [1], "supersedes_chunk_ids": [1]}
        for anchors in (False, True):
            strategy = DependencyStrategy(anchors=anchors, supersedes=False)
            strategy.record(1, {}, set())
            strategy.record(2, {}, {1})
            record = strategy.record(3, reply, {1, 2})
            self.assertEqual(record["parents"], [1, 2])
            self.assertEqual(record["anchors"], [1] if anchors else [])
            self.assertEqual(record["replaced"], [])
            self.assertNotIn("supersedes_chunk_ids", strategy.instructions)
            self.assertEqual("critical_anchor_ids" in strategy.instructions, anchors)

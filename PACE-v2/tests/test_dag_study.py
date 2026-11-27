from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from benchmarks.webwalker_full import FullRunAPI
from dag_pace.strategy import DependencyStrategy
from pace.memory import Summaries, Turn
from pace.policy import Settings
from pace.providers import ProviderError, Utf8Counter
from pace_v2.browser import Browser
from pace_v2.context import EvidenceBuilder, PreparedMemory
from pace_v2.dag_study import ARMS, COHORT, fresh_jobs
from pace_v2.evidence import Checklist, Fact


class StudyTests(unittest.TestCase):
    def test_repair_retries_same_query_only_on_temporary_search_limit(self):
        browser = object.__new__(Browser)
        browser.retry_rate_limits = True
        browser.public = Mock()
        failure = ProviderError("You.com service limit: Rate limited by You.com API")
        browser.public.search_one.side_effect = [failure, {"results":["result"]}]
        with patch("pace_v2.browser.sleep") as sleep:
            self.assertEqual(browser.new_search("original query"), {"results":["result"]})
            sleep.assert_called_once_with(15)
        self.assertEqual([c.args for c in browser.public.search_one.call_args_list], [("original query",)]*2)
        browser.public.search_one.side_effect = ProviderError("You.com HTTP 402")
        with patch("pace_v2.browser.sleep") as sleep, self.assertRaises(ProviderError):
            browser.new_search("q")
        sleep.assert_not_called()

    def test_bad_gateway_count_leaves_valid_action_usable(self):
        for usage in (None, [3], {"prompt_tokens": "bad"}, {"prompt_tokens": 280000}):
            with self.subTest(usage=usage), TemporaryDirectory() as root:
                api = FullRunAPI("https://example.org", "unused")
                api.job, api.output = (1, 1, "pace"), Path(root)
                reply = dict(usage=usage, choices=[dict(message=dict(content='{"tool":"finish","args":{"answer":"x"}}'))])
                with patch.object(api, "request_json", return_value=reply):
                    action = api.chat("model", [{"role":"user","content":"q"}], "actor",
                                      input_budget=80000,enforce_input_budget=False)
                self.assertEqual(action["args"]["answer"], "x")

    def test_v2_keeps_anchors_and_hides_superseded_checklist_facts(self):
        strategy = DependencyStrategy()
        book = Checklist("date", ["date"])
        book.strategy = strategy
        memory = PreparedMemory(lambda _: [1.0])
        for i in range(1, 5):
            memory.store(Turn("", "search", str(i)*90, "search"), Summaries("detail", "brief"))
        book.facts.append(Fact("F1", "obsolete", "obsolete", "S1", "url", 1))
        strategy.record(4, {"critical_anchor_ids":[2],"supersedes_chunk_ids":[1]}, {1,2,3})
        builder = EvidenceBuilder("system", "date", memory, Settings(20, budget=2000,
                                  pressure_mode="evidence-v2",compression_start_ratio=.05), Utf8Counter(), book,strategy)
        ctx = builder.build()
        self.assertEqual([r.chunk.id for r in ctx.selections], [2,3,4])
        self.assertEqual(ctx.selections[0].shown.name,"FULL")
        self.assertNotIn("obsolete", ctx.messages[1]["content"])
        self.assertEqual(ctx.adjustment["anchors"], [2])

    def test_main_run_excludes_all_reused_rows(self):
        reused = {"react": {str(n): {} for n in COHORT},
                  "pace-v2": {str(n): {} for n in (1,2,33,407)}}
        jobs = fresh_jobs(reused)
        self.assertEqual(len(set(jobs)), 76)
        self.assertEqual({(n,arm) for n in COHORT for arm in ARMS},
                         set(jobs) | {(int(n),a) for a, rows in reused.items() for n in rows})

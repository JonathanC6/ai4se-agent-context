import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from benchmarks.paper_pilot import FullHistory
from pace.agent import Tool
from pace.context import Builder,BudgetExceeded
from pace.memory import Summaries,Turn
from pace.policy import Settings
from pace.providers import Utf8Counter,ReplyFormatError,ProviderError
from pace_v2.browser import Archive,Reader,windows
from pace_v2.context import EvidenceBuilder,PreparedMemory
from pace_v2.evidence import Checklist,Passage
from pace_v2.episode import solve


class EvidenceTests(TestCase):
    def test_requires_source_observation_and_literal_value(self):
        book=Checklist("When?",["date of event"])
        p=Passage("S1","Event was March 14.","Event was March 14.","https://example.org")
        fact=dict(slot="F1",value="March 14",quote="Event was March 14.",source="S1")
        for bad in [dict(fact,quote="Event was March 15."),dict(fact,source="S2"),dict(fact,value="March 21")]:
            self.assertEqual(book.bind([bad],[p],1),[])
        self.assertEqual(book.bind([fact],[Passage("S1",p.text,"unrelated",p.url)],1),[])
        self.assertEqual(book.bind([fact],[p],1),["F1"])
        self.assertEqual(book.bind([fact],[p],2),[])

    def test_recent_compaction_preserves_original_and_local_cap(self):
        counter=Utf8Counter(); opts=Settings(20,budget=1100,pressure_mode="evidence-v2",compression_start_ratio=.9)
        mem=PreparedMemory(lambda _: [1.])
        turn=Turn("visit","visit","Navigation. "*500+"The project started in January 2020.","visit")
        mem.store(turn,Summaries("a date","date"))
        with self.assertRaises(BudgetExceeded):
            Builder("system","project started",mem,opts,counter,trace_window=True).build()
        ctx=EvidenceBuilder("system","project started",mem,opts,counter,Checklist("project",["start date"])).build()
        self.assertLessEqual(ctx.tokens,1100)
        self.assertIn("January 2020",ctx.messages[-1]["content"])
        self.assertIn(1,ctx.window["recent_excerpt_chars"])
        self.assertEqual(mem.chunks[0].turn.observation,turn.observation)

    def test_two_distant_windows(self):
        text="topic funding grant. "+"x"*47000+" topic funding grant on March 14."
        spans=windows(text,"topic funding grant")
        self.assertEqual(len(spans),2)
        self.assertLessEqual(sum(b-a for a,b in spans),24000)
        self.assertTrue(any("March 14" in text[a:b] for a,b in spans))

    def test_raw_page_saved_when_extraction_fails(self):
        obj=object.__new__(Reader)
        obj.api=None; obj.evidence=Archive(None); obj.log=lambda *a:None
        obj.load_document=lambda url,when:(url,"html","Funding began March 14.",{})
        with patch("pace_v2.browser.extract_page",side_effect=ReplyFormatError("bad reply")):
            row,=json.loads(obj.visit(dict(url="https://example.org",goal="funding")))
        self.assertFalse(row["read"])
        self.assertEqual(obj.evidence.sources[row["source_id"]].text,"Funding began March 14.")

    def test_failed_recovery_is_distinct_from_tool_execution(self):
        book=Checklist("q",["date","venue"])
        ctx=SimpleNamespace(selections=[])
        with patch("pace_v2.evidence.ask",return_value=dict(complete=False,slot="F1",target="C99",goal="event date")):
            review=book.review(None,"candidate",ctx,SimpleNamespace(sources={}))
            self.assertEqual(review["tool"],"search")
            self.assertIsNone(book.review(None,"candidate",ctx,SimpleNamespace(sources={})))
        self.assertEqual(book.check_recovery(None,review,[]),"no_new_support")


class ScriptedAPI:
    def __init__(self, replies, direct=None):
        self.replies = iter(replies)
        self.direct = direct
        self.last_input_tokens = {"actor": 40}

    def chat(self, *args, **kwargs):
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def post(self, path, body, role):
        assert role == "actor" and "response_format" not in body
        return {"choices": [{"finish_reason": "stop", "message": {"content": self.direct}}]}


class ActionTests(TestCase):
    def setUp(self):
        self.counter = SimpleNamespace(messages=lambda _:40, text=len, observe=lambda sent, actual:None)
        self.bad = ReplyFormatError("malformed action")
        self.search = {"tool":"search", "args":{"query":"event date"}}
        self.draft = {"tool":"finish", "args":{"answer":"March 14"}}

    def episode(self, api, arm="react", search=None):
        tool = Tool("search", search or (lambda _: "[]"))
        browser = SimpleNamespace(tools=lambda:{"search":tool}, evidence=Archive(api))
        book = Checklist("When?", ["event date"])
        review = {"complete":False, "slot":"F1", "target":"SEARCH", "goal":"event date",
                  "brief":"empty", "detailed":"empty", "facts":[]}
        with patch.object(Checklist,"plan",return_value=book), patch("pace_v2.evidence.ask",return_value=review):
            return solve("When?", "site", browser, api, self.counter, lambda _: [1.], arm, lambda _:None)

    def test_react_submits_direct_text_after_two_malformed_actions(self):
        api = ScriptedAPI([self.search, self.bad, self.bad], direct="March 14")
        result = self.episode(api)
        self.assertEqual((result["answer"], result["submission_state"]), ("March 14", "answer_only"))
        self.assertEqual(api.actor_log["format_attempt"], 3)

    def test_empty_final_response_is_a_normal_no_answer(self):
        result = self.episode(ScriptedAPI([self.search, self.bad, self.bad], direct=" "))
        self.assertEqual(result["status"], "no_valid_answer")
        self.assertIsNone(result["answer"])

    def test_truncated_output_gets_one_short_answer_on_the_same_evidence(self):
        api = ScriptedAPI([self.search, self.bad, self.bad])
        prompts = []
        def complete(path, body, role):
            prompts.append(body["messages"])
            reason, text = ("length", "partial") if len(prompts) == 1 else ("stop", '{"answer":"March 14"}')
            return {"choices":[{"finish_reason":reason, "message":{"content":text}}]}
        api.post = complete
        result = self.episode(api)
        self.assertEqual(len(prompts), 2)
        self.assertEqual(prompts[0][1:], prompts[1][1:])
        self.assertEqual((result["answer"], result["submission_state"]), ("March 14","concise_answer"))

    def test_retains_valid_draft_after_malformed_actions(self):
        api = ScriptedAPI([self.draft, self.bad, self.bad])
        result = self.episode(api, "pace-v2")
        self.assertEqual(result["drafts"][0]["answer"], "March 14")
        self.assertEqual((result["answer"], result["submission_state"]), ("March 14", "saved_draft"))

    def test_search_provider_failure_after_review_returns_saved_draft(self):
        def unavailable(_):
            raise ProviderError("search HTTP 402")
        result = self.episode(ScriptedAPI([self.draft]), "pace-v2", unavailable)
        self.assertEqual(result["answer"], "March 14")
        self.assertEqual(result["submission_state"], "saved_draft_after_tool_error")

    def test_search_provider_failure_without_draft_is_observed(self):
        def unavailable(_):
            raise ProviderError("search HTTP 402")
        result = self.episode(ScriptedAPI([self.search, self.draft]), search=unavailable)
        self.assertIn("Tool error", result["history"][0]["observation"])
        self.assertEqual(result["status"], "finished")

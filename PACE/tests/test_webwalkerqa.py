import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from benchmarks import webwalkerqa
from benchmarks.grading import LEGACY, SEMANTIC, grading_settings
from pace.providers import ReplyFormatError, json_object
from benchmarks.webwalker_snapshot import WINDOW, PageParser, site_tools, snapshot_digest


class WebWalkerTests(unittest.TestCase):
    def test_selection_and_site_boundary(self):
        def row(site, kind):
            return {"root_url": site, "info": {"type": kind}}

        rows = [row("other", "single_source"), row("site", "multi_source"),
                row("site", "single_source"), row("site", "multi_source")]
        self.assertEqual(webwalkerqa.select_rows(rows, "site", None), [3, 2])
        self.assertEqual(webwalkerqa.select_rows(rows, "site", [4, 2]), [4, 2])
        for invalid in ([1], [2, 2], [0], [5]):
            with self.assertRaises(ValueError):
                webwalkerqa.select_rows(rows, "site", invalid)

    def test_snapshot_scope_and_page_windows(self):
        root = "https://example.test/"
        parser = PageParser()
        parser.feed("<title>Agenda</title><nav>hidden</nav><main>" + "setup " * 800 +
                    "<p>Unique evidence</p></main>")
        page = parser.page(root)
        snapshot = {"pages": [page], "sha256": snapshot_digest([page])}
        tools = site_tools(snapshot)
        self.assertNotIn("hidden", page["text"])
        self.assertIn(root, tools["search"].call({"query": "agenda"}))
        visit = tools["visit"].call
        self.assertNotIn("Unique evidence", visit({"url": root}))
        self.assertIn("Unique evidence", visit({"url": root, "offset": WINDOW}))
        self.assertIn("Unique evidence", visit({"url": root, "find": "unique"}))
        with self.assertRaises(ValueError):
            visit({"url": "https://other.test/"})
        page["text"] += "changed"
        with self.assertRaises(ValueError):
            site_tools(snapshot)

    def test_standalone_dates_are_compared_without_a_model(self):
        api = Mock()
        row = {"question": "是哪天？", "answer": "三月十四日"}
        for answer in ("It is March 14th.", "is March 14", "14 March", "３月１４日"):
            with self.subTest(answer=answer):
                self.assertTrue(webwalkerqa.grade(row, answer, api, "model")["correct"])
        api.chat.assert_not_called()

    def test_existing_configuration_preserves_its_grader(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            self.assertEqual(grading_settings(path), {"grading_version": SEMANTIC})
            path.write_text('{}')
            self.assertEqual(grading_settings(path), {})
        api = Mock()
        api.chat.return_value = {"correct": True}
        verdict = webwalkerqa.grade({"question": "Q", "answer": "三月十四日"}, "March 14", api, "m", LEGACY)
        self.assertEqual(verdict["method"], "judge")
        api.chat.assert_called_once()

    def test_date_in_a_longer_answer_does_not_shortcut_the_judge(self):
        api = Mock()
        api.chat.return_value = {"correct": False, "reason": "wrong or incomplete"}
        for ref, answer in [("3月14日", "Not March 14"), ("3月14日", "March 13 or March 14"),
                            ("2024年3月14日", "March 14"), ("3月14日和李老师", "March 14")]:
            self.assertFalse(webwalkerqa.grade({"question": "Q", "answer": ref}, answer, api, "m")["correct"])
        self.assertEqual(api.chat.call_count, 4)

    def test_json_recovery_and_judge_isolation(self):
        self.assertEqual(json_object('Reply\n```json\n{"args": {"x": 1}}\n```'), {"args": {"x": 1}})
        api = Mock()
        api.chat.side_effect = [ReplyFormatError("malformed"), {"correct": True}]
        row = {"question": "Q", "answer": "gold", "info": {"golden_path": ["hidden path"]}}
        self.assertTrue(webwalkerqa.grade(row, "candidate", api, "model")["correct"])
        self.assertEqual(api.chat.call_count, 2)
        for call in api.chat.call_args_list:
            _, messages, purpose = call.args
            self.assertEqual(purpose, "judge")
            self.assertEqual(json.loads(messages[1]["content"]),
                             {"question": "Q", "prediction": "candidate", "reference": "gold"})

    def test_completed_episode_resumes_without_an_api_call(self):
        root = "https://example.test/"
        pages = [{"url": root, "title": "Home", "text": "Home."}]
        row = {"question": "Q", "answer": "private gold", "root_url": root,
               "info": {"type": "single_source", "source_website": ["private URL"]}}
        result = {"answer": "prediction", "status": "finished", "steps": [], "usage": {}, "solver_seconds": 1}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "site.json"
            path.write_text(json.dumps({"pages": pages, "root": root, "sha256": snapshot_digest(pages)}))
            argv = ["webwalkerqa", "run", "--root", root, "--rows", "1",
                    "--snapshot", str(path), "--out", str(Path(tmp) / "out")]
            with patch("sys.argv", argv), patch.object(webwalkerqa, "load_dataset", return_value=[row]), \
                 patch.object(webwalkerqa.API, "configured") as configured, \
                 patch.object(webwalkerqa, "solve", return_value=result) as solve, \
                 patch.object(webwalkerqa, "grade", return_value={"correct": False}) as grade:
                configured.return_value.usage = {}
                webwalkerqa.main()
                webwalkerqa.main()
                solve.assert_called_once()
                question, site, tools, _, config, strategy = solve.call_args.args
                self.assertIsNone(strategy)
                self.assertEqual((question, site, set(tools)), ("Q", root, {"search", "visit"}))
                self.assertNotIn("private", json.dumps(config))
                grade.assert_called_once()
                self.assertEqual(configured.call_count, 2)

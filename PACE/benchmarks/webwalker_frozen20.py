"""固定搜索候选，只替换网页读取器，分别保存 ReAct 的独立轨迹。"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
import re
from urllib.parse import urlsplit, unquote

from pace.agent import Tool
from pace.records import write_result
from pace.providers import ReplyFormatError
from .archive_reader import ArchiveBrowser
from .google_you import items
from .paper_pilot import episode
from .webwalker_archive20 import BASE
from .webwalker_full import FullRunAPI
from .webwalkerqa import ROOT, CACHE, load_dataset
from .you_public import PublicBrowser

OUT = ROOT / "results/webwalker-frozen20"
FIXTURE = OUT / "candidates.json"
BLOCK = re.compile(r"web[\s_-]*walker|webthinker|webdancer|huggingface\.co/datasets|/datasets?/|2504\.21776|hf-mirror\.com|golden_path", re.I)
SEARCH = '{"query":"terms"} lists this question\'s fixed candidates. All queries return the same ranked list. Each contains a document ID, host, type hint and topic words from the question. Use the ID as the visit URL.'
VISIT = '{"url":"document ID or discovered URL","goal":"facts to extract","offset":0,"as_of":"YYYY-MM-DD"} reads a document and extracts evidence. Omit as_of for current pages. For historical events you may request a dated snapshot; availability, PDF support and links depend on the reader. URL and goal may be parallel lists.'


class FrozenBrowser:
    def __init__(self, root, api, n, docs, reader, output):
        self.api = api
        self.reader = reader
        self.allowed = {root}
        self.urls = {}
        self.cards = []
        for i, doc in enumerate(docs, 1):
            url = doc["url"]
            if BLOCK.search(unquote(url)):
                raise ValueError("unsafe search fixture")
            ref = f"doc-{i}"
            self.urls[ref] = url
            self.allowed.add(url)
            parts = urlsplit(url)
            self.cards.append(dict(id=ref, host=parts.hostname,
                                   kind="pdf" if parts.path.lower().endswith(".pdf") else "web",
                                   keywords=doc["keywords"]))
        self.search_reply = json.dumps(self.cards, ensure_ascii=False)
        if reader == "archive":
            self.backend = ArchiveBrowser(api, n, output / "no-prior-history", output=output)
        elif reader == "you":
            self.backend = PublicBrowser(api, (None, None))

    def search(self, args):
        items(args.get("query"))
        return self.search_reply

    def excluded(self, url, content=""):
        return BLOCK.search(unquote(url)) or BLOCK.search(content)

    def visit(self, args):
        urls, goals = items(args.get("url")), items(args.get("goal"))
        if len(goals) == 1:
            goals *= len(urls)
        if len(urls) != len(goals):
            raise ValueError("supply one goal for each URL")
        offset = args.get("offset", 0)
        if type(offset) is not int or offset < 0:
            raise ValueError("invalid offset")
        result = []
        for ref, goal in zip(urls, goals):
            u = self.urls.get(ref, ref)
            try:
                if u not in self.allowed or self.excluded(u):
                    raise ValueError("choose a discovered URL or the root URL")
                if self.reader != "archive" and args.get("as_of"):
                    raise ValueError("dated snapshots unsupported by this reader")
                page, = json.loads(self.backend.visit(dict(args, url=u, goal=goal)))
                if self.excluded(page.get("source", u), page.get("extraction", "")):
                    raise ValueError("excluded benchmark-related page")
                if "links" in page:
                    page["links"] = [a for a in page["links"] if not self.excluded(a["url"], a.get("title", ""))]
                    self.allowed.update(a["url"] for a in page["links"])
            except (ValueError, ReplyFormatError) as exc:
                page = dict(url=u, read=False, message=str(exc)[:200])
            result.append(page)
        return json.dumps(result, ensure_ascii=False)

    def tools(self):
        return {"search": Tool(SEARCH, self.search), "visit": Tool(VISIT, self.visit)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reader", choices=("archive", "you"))
    parser.add_argument("--jobs", type=int, default=5)
    args = parser.parse_args()
    rows = load_dataset(CACHE)
    docs = json.loads(FIXTURE.read_text())
    base = json.loads((BASE / "config.json").read_text())
    if set(map(int, docs)) != set(base["rows"]) or len(docs) != 20:
        raise ValueError("wrong cohort")
    output = OUT / args.reader
    output.mkdir(parents=True, exist_ok=True)
    config = dict(base, protocol="frozen-search-read-v1", reader=args.reader,
                  search_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
    def make_browser(root, api, n):
        return FrozenBrowser(root, api, n, docs[str(n)], args.reader, output)
    run_cohort(rows, config, output, args.jobs, make_browser)


def run_cohort(rows, config, output, jobs, make_browser, *, encoder=None, strategy_factory=None,
               selected_rows=None):
    arm, = config["arms"]
    if arm not in ("react", "pace", "dag-pace") or (arm != "react") != (encoder is not None):
        raise ValueError("encoder and arm mismatch")
    if (arm == "dag-pace") != (strategy_factory is not None):
        raise ValueError("strategy and arm mismatch")
    with (output / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = output / "config.json"
        if path.exists() and json.loads(path.read_text()) != config:
            raise ValueError("configuration changed")
        write_result(path, config)
        def one(n):
            job = (1, n, arm)
            def api_factory():
                api = FullRunAPI.configured()
                api.job, api.output = job, output
                return api
            def tools(root, api):
                return make_browser(root, api, n).tools()
            return episode(job, config, rows, None, encoder, output, tools, api_factory,
                           strategy_factory=strategy_factory)
        with ThreadPoolExecutor(jobs) as pool:
            scheduled = config["rows"] if selected_rows is None else selected_rows
            if not set(scheduled) <= set(config["rows"]):
                raise ValueError("selected row outside the saved cohort")
            futures = {pool.submit(one, n): n for n in scheduled}
            failed = []
            for future in as_completed(futures):
                try:
                    print(config["reader"], future.result(), flush=True)
                except Exception as exc:
                    failed.append(futures[future])
                    print("incomplete", config["reader"], futures[future], type(exc).__name__, str(exc)[:180], flush=True)
            if failed:
                raise SystemExit(f"resume incomplete rows: {failed}")


if __name__ == "__main__":
    main()

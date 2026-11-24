"""动态搜索按原查询缓存。网页读取、模型和裁判沿用固定候选组。"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib
import json
import re
import sys
import threading
import time
from urllib.parse import unquote, urlsplit

from pace.agent import Tool
from pace.providers import ProviderError
from pace.records import write_result
from .google_you import items
from .paper_pilot import DenseEncoder, ENCODER
from .webwalker_frozen20 import FrozenBrowser, VISIT, OUT as FROZEN, run_cohort
from .webwalkerqa import ROOT, CACHE, load_dataset

OUT = ROOT / "results/webwalker-dynamic20"
SEARCH = '{"query":"search terms"} searches the web. You can refine your search or supply a list of queries. Returns up to ten results per query with title, snippet and URL.'
MIRROR = re.compile(r"web[\s_-]*walker[\s_-]*(qa|test|rl)|golden_path.{0,80}source_website|source_website.{0,80}golden_path", re.I)
ANSWER = re.compile(r'''["']?answer["']?\s*[:：]|ground.truth|gold(?:en)? answer|参考答案|标准答案''', re.I)
LOCKS = [threading.Lock() for _ in range(128)]


def normalized(value):
    return re.sub(r"[^\w]", "", value.casefold())


@lru_cache(maxsize=1)
def question_signatures():
    return [normalized(row["question"]) for row in load_dataset(CACHE)]


def exclusion(url, content=""):
    path = unquote(url).lower()
    if MIRROR.search(path) or (MIRROR.search(content) and re.search(
            r"dataset|jsonl|parquet|test set|题库|数据集|benchmark question", content, re.I)):
        return "benchmark copy"
    compact = normalized(content)
    if ANSWER.search(content) and any(q in compact for q in question_signatures()):
        return "benchmark question with answer key"
    return ""


def key(query):
    return hashlib.sha256(query.encode()).hexdigest()


def filtered(query, rows):
    results, excluded, seen = [], [], set()
    for row in rows:
        url = row["url"]
        reason = exclusion(url, row["title"] + " " + row["snippet"])
        if reason:
            excluded.append(dict(url=url, reason=reason))
        elif url not in seen and urlsplit(url).scheme in ("http", "https"):
            seen.add(url)
            results.append({k: row[k] for k in ("title", "snippet", "url")})
    return dict(query=query, results=results[:10], excluded=excluded)


class DynamicBrowser(FrozenBrowser):
    def __init__(self, root, api, n, output=None):
        super().__init__(root, api, n, [], "archive", output or OUT)

    def excluded(self, url, content=""):
        return exclusion(url, content)

    def search_one(self, query):
        digest = key(query)
        spool = OUT / "search"
        cached = spool / f"{digest}.result.json"
        with LOCKS[int(digest[:2], 16) % len(LOCKS)]:
            hit = cached.exists()
            if not hit:
                write_result(spool / f"{digest}.query.json", {"query":query})
                for _ in range(600):
                    if cached.exists():
                        break
                    time.sleep(1)
                else:
                    raise ProviderError("search backend timeout")
            entry = json.loads(cached.read_text())
            if entry["query"] != query:
                raise ValueError("query cache mismatch")
            self.backend.log("query", dict(key=digest, hit=hit))
            return dict(query=query, results=entry["results"])

    def search(self, args):
        queries = items(args.get("query"))
        with ThreadPoolExecutor(min(len(queries), 4)) as pool:
            results = list(pool.map(self.search_one, queries))
        for response in results:
            self.allowed.update(item["url"] for item in response["results"])
        return json.dumps(results, ensure_ascii=False)

    def tools(self):
        return {"search": Tool(SEARCH, self.search), "visit": Tool(VISIT.replace("document ID or discovered URL","discovered URL"), self.visit)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "pending", "answer"))
    parser.add_argument("--arm", choices=("react","pace"), default="react")
    parser.add_argument("--jobs", type=int, default=5)
    args = parser.parse_args()
    spool = OUT / "search"
    if args.action == "pending":
        print(json.dumps([json.loads(p.read_text())["query"] for p in sorted(spool.glob("*.query.json"))
                          if not p.with_name(p.name.replace(".query.", ".result.")).exists()], ensure_ascii=False))
    elif args.action == "answer":
        for item in json.load(sys.stdin):
            query = item["query"]
            digest = key(query)
            if not (spool / f"{digest}.query.json").exists():
                raise ValueError("query was not requested")
            target = spool / f"{digest}.result.json"
            if not target.exists():
                write_result(target, filtered(query, item["results"]))
    else:
        OUT.mkdir(parents=True, exist_ok=True)
        config = json.loads((FROZEN / "archive/config.json").read_text())
        del config["search_sha256"]
        config.update(protocol="dynamic-query-v1", search_backend="public-web-search", search_limit=10)
        output = OUT if args.arm == "react" else OUT.with_name(OUT.name + "-pace")
        encoder = None
        if args.arm == "pace":
            if config != json.loads((OUT / "config.json").read_text()) or config["encoder"] != ENCODER:
                raise ValueError("ReAct configuration mismatch")
            config = dict(config, arms=["pace"], summary_model=config["model"])
            encoder = DenseEncoder()
            output.mkdir(parents=True, exist_ok=True)
        def make_browser(root, api, n):
            return DynamicBrowser(root, api, n, output)
        run_cohort(load_dataset(CACHE), config, output, args.jobs, make_browser, encoder=encoder)


if __name__ == "__main__":
    main()

"""两组共用的检索、原文归档和按目标重读。"""
import json
import re
from time import sleep
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from benchmarks.google_you import items
from benchmarks.paper_pilot import extract_page
from benchmarks.research_browser import ResearchBrowser, ResearchReader, cache_entry
from benchmarks.source_evidence import SourceEvidence
from benchmarks.webwalker_dynamic20 import OUT as OLD_SEARCH, filtered, key
from benchmarks.you_public import PublicBrowser
from pace.providers import ProviderError
from pace.records import write_result


def terms(text):
    text = text.casefold()
    words = set(re.findall(r"[a-z0-9]{2,}", text)) - set("and the with from for that what which when".split())
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        words.update(run[i:i+2] for i in range(max(1, len(run)-1)))
    return words


def windows(text, goal):
    """最多读取 24K 字符。挑两个相距较远的目标段落，减少长文首段偏差。"""
    if len(text) <= 24000:
        return [(0, len(text))]
    keys = terms(goal)
    points = sorted(range(0, len(text), 800),
                    key=lambda p: -len(keys & terms(text[p:p+1600])))
    starts = []
    for pos in points:
        start = min(max(0, pos-4500), len(text)-12000)
        if all(abs(start-other) >= 12000 for other in starts):
            starts.append(start)
            if len(starts) == 2:
                break
    if len(starts) == 1:
        # 匹配词集中在中间时，从未覆盖的两端选更远的一端。
        start = starts[0]
        other = 0 if start >= len(text)-12000-start else len(text)-12000
        if abs(start-other) >= 12000:
            starts.append(other)
    return [(s, s+12000) for s in sorted(starts)]


class Archive(SourceEvidence):
    def reread(self, args):
        sid, goal = args.get("source_id"), args.get("goal")
        if sid not in self.sources or not isinstance(goal, str) or not goal.strip():
            raise ValueError("choose a saved source_id and a missing fact")
        source = self.sources[sid]
        if "offset" in args or "find" in args:
            try:
                return super().reread(args)
            except ValueError as exc:
                if "literal phrase not found" not in str(exc):
                    raise
        spans = windows(source.text, goal)
        cache_key = (sid, goal, tuple(spans))
        if cache_key not in self.cache:
            passages = [{"window": [a,b], "extraction": extract_page(self.api, source.url, goal, source.text, a,b)}
                        for a,b in spans]
            self.cache[cache_key] = json.dumps(dict(source_id=sid, source=source.url, passages=passages),
                                                ensure_ascii=False)
        return self.cache[cache_key]


class Reader(ResearchReader):
    def visit(self, args):
        urls, goals = items(args.get("url")), items(args.get("goal"))
        if len(goals) == 1:
            goals *= len(urls)
        if len(urls) != len(goals):
            raise ValueError("supply one goal per URL")
        when, offset = args.get("as_of"), args.get("offset")
        if when is not None:
            if not isinstance(when, str):
                raise ValueError("as_of must be YYYY-MM-DD")
            date.fromisoformat(when)
        if offset is not None and (type(offset) is not int or offset < 0):
            raise ValueError("invalid offset")
        result = []
        for url, goal in zip(urls, goals):
            row = dict(url=url, read=False, as_of=when)
            try:
                final, fmt, text, links = self.load_document(url, when)
                start = self.extraction_offset(text, goal, offset)
                if not text.strip() or start >= len(text):
                    raise ValueError("no readable text at offset")
                end = min(start+24000, len(text))
                # 先保存正文。提取模型失败时，仍可通过 S 编号找回。
                row.update(self.evidence.remember(final, text, start, end), source=final, format=fmt)
                keys = terms(goal)
                ranked = sorted(links, key=lambda u:-len(keys & terms(links[u]+" "+u)))
                row["links"] = [dict(url=u,title=links[u][:140]) for u in ranked
                                if urlsplit(u).scheme in ("http","https")][:12]
                row["extraction"] = extract_page(self.api, final, goal, text, start, end)
                row["read"] = True
            except (ProviderError, OSError, ValueError, LookupError) as exc:
                row["message"] = str(exc)[:180]
            self.log("visit", {k:v for k,v in row.items() if k not in ("extraction","links")})
            result.append(row)
        return json.dumps(result, ensure_ascii=False)


class Browser(ResearchBrowser):
    search_provider = "you-public"
    def __init__(self, root, api, n, output, search_cache):
        super().__init__(root, api, n, output)
        self.search_cache = Path(search_cache)
        self.evidence = Archive(api, output/"sources", rank_rereads=True)
        self.backend = Reader(api, n, output, (None,None), self.evidence)
        self.public = PublicBrowser(api, (None,None))
        self.retry_rate_limits = False

    def new_search(self, query):
        # 限流补跑仍发送原查询。只给临时限流留出冷却时间，硬配额错误直接返回。
        waits = (15, 45, 90) if self.retry_rate_limits else ()
        for attempt in range(len(waits) + 1):
            try:
                return self.public.search_one(query)
            except ProviderError as exc:
                if attempt == len(waits) or not search_rate_limit(str(exc)):
                    raise
                sleep(waits[attempt])

    def search_one(self, query):
        original = OLD_SEARCH/"search"/(key(query)+".result.json")
        with cache_entry(self.search_cache, query) as dest:
            if dest.exists():
                entry = json.loads(dest.read_text())
                hit = True
            elif original.exists():
                entry = json.loads(original.read_text())
                entry["provider"] = "historical-public"
                hit = True
                write_result(dest, entry)
            else:
                response = self.new_search(query)
                entry = filtered(query, response["results"])
                entry["provider"] = self.search_provider
                hit = False
                write_result(dest, entry)
        if entry["query"] != query:
            raise ValueError("query cache mismatch")
        self.backend.log("query", dict(key=key(query), hit=hit, backend=entry["provider"]))
        return dict(query=query, results=entry["results"])


def search_rate_limit(message):
    text = message.casefold()
    return "you.com" in text and ("rate limit" in text or "http 429" in text)

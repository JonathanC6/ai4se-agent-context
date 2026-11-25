"""WebWalkerQA 统一工具。不同组共享冻结的搜索排序和整页内容，证据访问权限按题隔离。"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import re
from urllib.parse import urljoin, urlsplit

from pypdf.errors import PyPdfError
from pace.agent import Tool
from pace.providers import ProviderError
from pace.records import write_result
from .archive_reader import ArchiveBrowser, document, public_url
from .google_you import PaperBrowser, optional_credentials
from .source_evidence import SourceEvidence
from .webwalker_dynamic20 import DynamicBrowser, exclusion, filtered
from .webwalker_live import terms
from .webwalkerqa import ROOT
from .you_public import PublicBrowser

PROTOCOL = "research-web-v1"
CACHE = ROOT / ".cache" / PROTOCOL
WINDOW = 24000


def browser_settings():
    search_key, contents_key = optional_credentials()
    return dict(protocol=PROTOCOL, search_backend="google-serper" if search_key else "public-web-search",
                reader="you-contents+archive" if contents_key else "you-free+archive", search_limit=10)


@contextmanager
def cache_entry(directory, identity):
    key = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (key + ".json")
    # 多进程实验也只抓一次，后来的组读取相同页面快照或失败记录。
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield path


def markdown_links(url, page):
    links = {}
    for label, href in re.findall(r"(?<!!)\[([^\]\n]*)\]\(<?([^\s)>]+)>?(?:\s+[^)]*)?\)", page):
        target = urljoin(url, href)
        if urlsplit(target).scheme in ("https", "http"):
            links[target] = label
    return links


class ResearchReader(ArchiveBrowser):
    def __init__(self, api, n, output, keys, evidence):
        super().__init__(api, n, output / "no-prior-history", output=output)
        self.evidence = evidence
        self.you = PaperBrowser(api, keys) if keys[1] else PublicBrowser(api, keys)
        self.provider = "you-contents" if keys[1] else "you-free"

    def fetch_document(self, url, when):
        fallback_reason = None
        if not when:
            try:
                public_url(url)
                page = self.you.fetch_pages([url])
                markdown = next((p.get("markdown") for p in page if p.get("url") == url), None)
                if not isinstance(markdown, str) or not markdown.strip():
                    raise ValueError("You.com returned no Markdown")
                return dict(source=url, format="markdown", text=markdown,
                            links=markdown_links(url, markdown), backend=self.provider)
            except (ProviderError, KeyError, TypeError, OSError, ValueError) as exc:
                fallback_reason = str(exc)[:180]
        final, fmt, text, links = document(url, when)
        return dict(source=final, format=fmt, text=text, links=links,
                    backend="wayback" if when else "direct", fallback_reason=fallback_reason)

    def load_document(self, url, when):
        with cache_entry(CACHE / "pages", [self.provider, url, when]) as path:
            hit = path.exists()
            if hit:
                page = json.loads(path.read_text())
            else:
                try:
                    page = self.fetch_document(url, when)
                    if exclusion(page["source"], page["text"]):
                        raise ValueError("excluded benchmark-related page")
                except (OSError, ValueError, LookupError, PyPdfError) as exc:
                    page = dict(error=str(exc)[:180])
                write_result(path, page)
        self.log("document", dict(url=url, as_of=when, hit=hit, cache_id=path.stem,
                                  backend=page.get("backend"), error=page.get("error"),
                                  fallback_reason=page.get("fallback_reason")))
        if "error" in page:
            raise ValueError(page["error"])
        return page["source"], page["format"], page["text"], page["links"]

    def extraction_offset(self, text, goal, requested):
        if requested is not None or len(text) <= WINDOW:
            return requested or 0
        # 长文先在整篇范围内匹配目标，再把连续窗口交给提取模型。
        keys = terms(goal)
        starts = list(range(0, len(text) - WINDOW, WINDOW // 2)) + [len(text) - WINDOW]
        return max(starts, key=lambda i: len(keys & terms(text[i:i + WINDOW])))


class ResearchBrowser(DynamicBrowser):
    def __init__(self, root, api, n, output, *, rank_rereads=False):
        super().__init__(root, api, n, output)
        keys = optional_credentials()
        self.google = PaperBrowser(api, keys) if keys[0] else None
        self.evidence = SourceEvidence(api, output / "sources", rank_rereads=rank_rereads)
        self.backend = ResearchReader(api, n, output, keys, self.evidence)

    def search_one(self, query):
        if self.google is None:
            return super().search_one(query)
        with cache_entry(CACHE / "serper", query) as path:
            hit = path.exists()
            if hit:
                entry = json.loads(path.read_text())
            else:
                response = self.google.search_one(query)
                entry = filtered(query, response["results"])
                write_result(path, entry)
        self.backend.log("query", dict(key=path.stem, hit=hit, backend="google-serper"))
        return dict(query=query, results=entry["results"])

    def tools(self):
        tools = super().tools()
        tools["visit"] = Tool('{"url":"discovered URL","goal":"fact to find","offset":0,"as_of":"YYYY-MM-DD"} '
                              'reads a page, including PDFs. Live pages use You.com Markdown with direct fallback. '
                              'Historical dates request Wayback. Omit offset to select a goal-relevant passage. '
                              'Long pages can be revisited by offset. Returns evidence and source_id for reread.', self.visit)
        tools["reread"] = self.evidence.tool()
        return tools

"""按代理选择的 URL 获取当前网页、Wayback 快照或 PDF。"""
import hashlib
import io
import ipaddress
import json
import re
import socket
import time
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urljoin, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from pypdf import PdfReader
from pypdf.errors import PyPdfError
from pace.agent import Tool
from pace.providers import ProviderError
from pace.records import write_result
from .google_you import items
from .paper_pilot import extract_page
from .webwalker_live import Links, terms
from .webwalker_snapshot import USER_AGENT
from .webwalkerqa import ROOT
from .you_public import PublicBrowser

BASE = ROOT / "results/webwalker-archive20"
LIMIT = 24_000_000


def public_url(url):
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password or p.port not in (80, 443, None):
        raise ValueError("expected a public HTTP(S) URL")
    if any(not ipaddress.ip_address(a[4][0]).is_global for a in socket.getaddrinfo(p.hostname, p.port or 443)):
        raise ValueError("expected a public internet host")


class Redirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url):
    public_url(url)
    url = quote(url, safe=":/?#[]@!$&'()*+,;=%")
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with build_opener(Redirect()).open(req, timeout=22) as response:
        data = response.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError("document exceeds 24 MB")
        return data, response.geturl(), response.headers.get_content_type(), response.headers.get_content_charset()


def archived(url, when, *, use_cdx=True):
    api = "https://archive.org/wayback/available?" + urlencode({"url": url, "timestamp": when.replace("-", "")})
    if not use_cdx:
        snap = json.loads(download(api)[0]).get("archived_snapshots", {}).get("closest", {})
        if not snap.get("available") or snap.get("status") != "200":
            raise ValueError("no snapshot located")
        return "https://web.archive.org/web/" + snap["timestamp"] + "id_/" + url
    try:
        snap = json.loads(download(api)[0]).get("archived_snapshots", {}).get("closest", {})
    except (OSError, ValueError):
        snap = {}
    if snap.get("available") and snap.get("status") == "200":
        stamp = snap["timestamp"]
    else:
        # availability 接口偶尔返回空对象；再查 CDX 的真实抓取记录。
        params = {"url": url, "from": when[:4], "to": when[:4], "output": "json",
                  "filter": "statuscode:200", "fl": "timestamp,original", "collapse": "timestamp:8"}
        records = json.loads(download("https://web.archive.org/cdx/search/cdx?" + urlencode(params))[0])[1:]
        if not records:
            raise ValueError("no snapshot located")
        def distance(record):
            d = record[0][:8]
            captured = date(int(d[:4]), int(d[4:6]), int(d[6:]))
            return abs(captured - date.fromisoformat(when))
        stamp, url = min(records, key=distance)
    return "https://web.archive.org/web/" + stamp + "id_/" + url


@lru_cache(maxsize=64)
def document(url, when, use_cdx=True):
    target = archived(url, when, use_cdx=use_cdx) if when else url
    data, final, mime, charset = download(target)
    if data[:1024].find(b"%PDF-") >= 0:
        reader = PdfReader(io.BytesIO(data), strict=False)
        text = "\n".join(f"[p.{i}] {p.extract_text() or ''}" for i, p in enumerate(reader.pages, 1))
        if not re.sub(r"\[p\.\d+\]", "", text).strip():
            raise ValueError("PDF has no extractable text")
        return final, "pdf", text, {}
    if mime not in ("application/xhtml+xml", "text/html", "text/plain"):
        raise ValueError("unsupported response type " + mime)
    if mime == "text/plain":
        return final, "text", data.decode(charset or "utf-8", errors="replace"), {}
    html = Links()
    meta = re.search(rb'charset\s*=\s*["\']?([A-Za-z0-9_.-]+)', data[:4096], re.I)
    html.feed(data.decode(charset or (meta[1].decode() if meta else "utf-8"), errors="replace"))
    links = {urljoin(url, href): label for href, label in html.labels.items() if href}
    return final, "html", html.page(url)["text"], links


class ArchiveBrowser(PublicBrowser):
    def __init__(self, api, n, previous, *, use_cdx=True, output=BASE):
        self.output = output
        self.use_cdx = use_cdx
        super().__init__(api, (None, None))
        self.n = n
        self.cached_queries = {}
        if previous.exists():
            for t in json.loads(previous.read_text())["history"]:
                if t["kind"] == "search" and t["observation"].startswith("["):
                    for query in json.loads(t["observation"]):
                        self.cached_queries[query["query"]] = query

    def search_one(self, query):
        if query in self.cached_queries:
            self.log("old_search", query)
            return self.cached_queries[query]
        # 搜索桥只接收 agent 的原始查询；独立于答案、标注 URL 和人工证据。
        key = hashlib.sha256(query.encode()).hexdigest()
        spool = self.output / "search"
        request = spool / f"{self.n}-{key}.query.json"
        result = spool / f"{key}.result.json"
        write_result(request, {"query": query})
        for _ in range(1200):
            if result.exists():
                self.log("web_search", query)
                return json.loads(result.read_text())
            time.sleep(1)
        raise ProviderError("timed out waiting for public search")

    def log(self, kind, info):
        with (self.output / f"reader-{self.n}.jsonl").open("a") as f:
            f.write(json.dumps([kind, info], ensure_ascii=False) + "\n")

    def visit(self, args):
        urls, goals = items(args.get("url")), items(args.get("goal"))
        if len(goals) == 1:
            goals *= len(urls)
        if len(goals) != len(urls):
            raise ValueError("supply one goal for each URL")
        when = args.get("as_of")
        if when is not None:
            if not isinstance(when, str):
                raise ValueError("as_of must be YYYY-MM-DD")
            date.fromisoformat(when)
        offset = args.get("offset", 0)
        if type(offset) != int or offset < 0:
            raise ValueError("invalid offset")
        result = []
        for url, goal in zip(urls, goals):
            try:
                final, fmt, text, links = document(url, when, self.use_cdx)
                if not text.strip() or offset >= len(text):
                    raise ValueError("no readable text at offset")
                end = min(offset + 24000, len(text))
                extract = extract_page(self.api, final, goal, text, offset, end)
                keys = terms(goal)
                ranked = sorted(links, key=lambda u:len(keys & terms(links[u] + " " + u)), reverse=True)
                menu = [{"url": u, "title": links[u][:140]} for u in ranked if urlsplit(u).scheme in ("https","http")][:12]
                row = dict(url=url, read=True, source=final, format=fmt, as_of=when, extraction=extract, links=menu)
            except (OSError, ValueError, LookupError, PyPdfError) as exc:
                msg = f"HTTP {exc.code}" if isinstance(exc, HTTPError) else str(exc)[:180]
                row = dict(url=url, read=False, as_of=when, message=msg)
            self.log("visit", {k:v for k,v in row.items() if k not in ("extraction","links")})
            result.append(row)
        return json.dumps(result, ensure_ascii=False)

    def tools(self):
        tools = super().tools()
        tools["search"] = Tool(tools["search"].description.replace("You.com", "the web"), self.search)
        tools["visit"] = Tool('{"url":"URL","goal":"facts to extract","offset":0,"as_of":"YYYY-MM-DD"} reads HTML or PDF, including document links. Omit as_of for live pages. For historical events or changed/unavailable pages, request a Wayback snapshot near the desired date. Check the returned capture timestamp. URL and goal can be parallel lists; offset is optional.', self.visit)
        return tools

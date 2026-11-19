"""从给定入口浏览公开网页。搜索只使用本轮已发现的同站链接。"""
import hashlib
import json
import re
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urldefrag, urljoin, urlsplit, unquote
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pace.agent import Tool
from pace.records import write_result
from .paper_pilot import extract_page
from .webwalker_snapshot import PageParser, USER_AGENT
from .webwalkerqa import CACHE

PAGE_CACHE = CACHE / "full-live-v1"
locks = [threading.Lock() for _ in range(128)]


def hostname(url):
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def allowed(url, sites):
    try:
        p = urlsplit(url)
        return (p.scheme in {"http", "https"} and p.username is None and p.password is None
                and p.port in {None, 80, 443} and hostname(url) in sites)
    except ValueError:
        return False


class SiteRedirect(HTTPRedirectHandler):
    def __init__(self, sites):
        self.sites = sites

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl, self.sites):
            raise ValueError("redirect outside the benchmark site")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Links(PageParser):
    def __init__(self):
        super().__init__()
        self.anchor = None
        self.labels = {}

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        if tag == "a":
            self.anchor = dict(attrs).get("href")

    def handle_data(self, text):
        super().handle_data(text)
        if self.anchor and text.strip():
            self.labels[self.anchor] = (self.labels.get(self.anchor, "") + " " + text.strip()).strip()[:180]

    def handle_endtag(self, tag):
        if tag == "a":
            self.anchor = None
        super().handle_endtag(tag)


def read_page(url, sites):
    if not allowed(url, sites):
        raise ValueError("choose a discovered URL on the benchmark site")
    digest = hashlib.sha256(url.encode()).hexdigest()
    path = PAGE_CACHE / f"{digest}.json"
    with locks[int(digest[:2], 16) % len(locks)]:
        if path.exists():
            return json.loads(path.read_text())
        try:
            # 有些站内 href 包含空格或中文；保留已编码的转义及查询分隔符。
            req = Request(quote(url, safe=":/?#[]@!$&'()*+,;=%"), headers={"User-Agent": USER_AGENT})
            with build_opener(SiteRedirect(sites)).open(req, timeout=15) as response:
                if response.headers.get_content_type() not in ("text/html", "application/xhtml+xml", "text/plain"):
                    raise ValueError("unsupported response type")
                data = response.read(2_000_000)
                final = response.geturl()
                meta = re.search(rb'charset\s*=\s*["\']?([a-zA-Z0-9_.-]+)', data[:4096], re.I)
                charset = response.headers.get_content_charset() or (meta[1].decode() if meta else "utf-8")
            parser = Links()
            parser.feed(data.decode(charset, errors="replace"))
            page = parser.page(final)
            page["text"] = page["text"][:240000]
            links = {}
            for href in sorted(parser.links):
                try:
                    child = urldefrag(urljoin(final, href))[0]
                except ValueError:
                    continue
                if allowed(child, sites) and Path(urlsplit(child).path).suffix.lower() not in (
                        ".jpg", ".png", ".svg", ".pdf", ".zip", ".mp4", ".gif", ".jpeg", ".docx"):
                    links[child] = parser.labels.get(href, "")
            page["links"] = links
        except (OSError, ValueError, LookupError) as exc:
            reason = f"HTTP {exc.code}" if isinstance(exc, HTTPError) else type(exc).__name__ + ": " + str(exc)[:160]
            raise ValueError(reason) from None
        write_result(path, page)
        return page


def terms(text):
    # 中文使用相邻双字，英文使用完整单词。
    chunks = re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text.casefold())
    return {term for chunk in chunks for term in (
        [chunk] if chunk.isascii() or len(chunk) == 1 else [chunk[i:i+2] for i in range(len(chunk)-1)])}


class Browser:
    def __init__(self, root, api, sites):
        self.root, self.api, self.sites = root, api, sites
        self.labels = {root: "Site homepage"}
        self.pages = {}
        self.errors = {}

    def load(self, url):
        if url not in self.labels:
            raise ValueError("choose a URL discovered by search or visit")
        if url in self.errors:
            raise ValueError(self.errors[url])
        if url not in self.pages:
            try:
                page = read_page(url, self.sites)
            except ValueError as exc:
                self.errors[url] = str(exc)
                raise
            self.pages[url] = page
            self.labels.update(page["links"])
        return self.pages[url]

    def ranked(self, query, labels):
        keys = terms(query)
        return sorted(labels, key=lambda u: -len(keys & terms(labels[u] + " " + unquote(urlsplit(u).path))))[:10]

    def search(self, args):
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("supply a text query")
        self.load(self.root)
        return "\n".join(f"{self.labels[u]} | {u}" for u in self.ranked(query, self.labels))

    def visit(self, args):
        url, goal, offset = args.get("url"), args.get("goal"), args.get("offset", 0)
        if not isinstance(url, str) or not isinstance(goal, str) or not goal.strip():
            raise ValueError("supply a discovered URL and a text goal")
        page = self.load(url)
        text = page["text"]
        if type(offset) is not int or offset < 0 or (offset and offset >= len(text)):
            raise ValueError("invalid character offset")
        links = page["links"]
        menu = "\n".join(f"{links[u]} | {u}" for u in self.ranked(goal, links))
        body = extract_page(self.api, url, goal, text, offset, min(len(text), offset+24000)) if text else "No page text."
        return body + "\nDiscovered links:\n" + menu

    def tools(self):
        return {"search": Tool('{"query":"words"} ranks up to ten links discovered on the root or previously visited pages. Visit links to explore deeper.', self.search),
                "visit": Tool('{"url":"URL","goal":"what to extract","offset":0} reads a page, extracts evidence and discovers links. Offset is optional.', self.visit)}

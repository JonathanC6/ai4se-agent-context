"""Build and browse a frozen site index without consulting WebWalkerQA annotations."""
import hashlib
import json
import math
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib import robotparser
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from pace.agent import Tool
from pace.records import write_result


USER_AGENT = "PACE-course-research/1.0"
WINDOW = 4200


def fetch(url, timeout=25):
    with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=timeout) as response:
        data = response.read(6_000_001)
        if len(data) > 6_000_000:
            raise ValueError("download exceeds 6 MB")
        return data


class PageParser(HTMLParser):
    hidden = {"script", "style", "nav", "footer", "noscript", "svg", "template"}
    blocks = {"p", "div", "article", "main", "li", "table", "tr", "br", "h1", "h2", "h3", "h4", "section"}
    void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
            "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.parts = []
        self.main = []
        self.title = []
        self.links = set()

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.add(href)
        if tag in self.blocks:
            self.handle_data("\n")
        if tag in ("td", "th"):
            self.handle_data(" | ")
        if tag not in self.void:
            parent = self.stack[-1] if self.stack else ("", False, False)
            primary = tag in ("main", "article") or dict(attrs).get("id") == "main"
            self.stack.append((tag, parent[1] or tag in self.hidden, parent[2] or primary))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if tag in self.blocks:
            self.handle_data("\n")

    def handle_data(self, text):
        if self.stack and self.stack[-1][1]:
            return
        self.parts.append(text)
        if self.stack and self.stack[-1][2]:
            self.main.append(text)
        if self.stack and self.stack[-1][0] == "title":
            self.title.append(text)

    def page(self, url, *, fallback_empty=True):
        text = "".join(self.main)
        if not self.main or (fallback_empty and not text.strip()):
            text = "".join(self.parts)
        lines = [" ".join(line.split()) for line in text.splitlines()]
        return {"url": url, "title": " ".join("".join(self.title).split()) or url,
                "text": "\n".join(line for line in lines if line)}


def prepare_site(root, path):
    """Freeze a public site's HTML sitemap. Its canonical hostname can be an alias."""
    if urlsplit(root).scheme != "https":
        raise ValueError("snapshot preparation requires an HTTPS site")
    robot = robotparser.RobotFileParser()
    try:
        robot.parse(fetch(urljoin(root, "/robots.txt")).decode().splitlines())
    except HTTPError as exc:
        if exc.code != 404:
            raise
        robot.parse([])
    sitemap = urljoin(root, "/sitemap.xml")
    if not robot.can_fetch(USER_AGENT, sitemap):
        raise ValueError("sitemap disallowed by robots.txt")
    # 旧会议网站没有 sitemap 时，从首页按层遍历同站 HTML。
    try:
        tree = ElementTree.fromstring(fetch(sitemap))
    except HTTPError as exc:
        if exc.code != 404:
            raise
        tree = None
    urls = {root}
    if tree is not None:
        if tree.tag.rsplit("}", 1)[-1] != "urlset":
            raise ValueError("expected an HTML page urlset")
        for loc in tree.findall("{*}url/{*}loc"):
            parts = urlsplit(loc.text or "")
            if not re.search(r"\.(?:pdf|xml|txt|zip|jpg|png|gz)$", parts.path, re.I):
                page_path = parts.path
                # ACL 2024 的 sitemap 带 GitHub 仓库前缀，官网从域名根目录提供相同页面。
                if parts.hostname == "github.com" and page_path.startswith("/acl-org/acl-2024/") and urlsplit(root).hostname == "2024.aclweb.org":
                    page_path = page_path[len("/acl-org/acl-2024"):]
                urls.add(urljoin(root, "/" + page_path.lstrip("/")))

    def download(url):
        if not robot.can_fetch(USER_AGENT, url):
            return url, None, "robots.txt", set()
        for attempt in range(2):
            try:
                html = fetch(url).decode("utf-8", errors="replace")
                parser = PageParser()
                parser.feed(html)
                page = parser.page(url)
                if not page["text"]:
                    raise ValueError("empty page")
                links = set()
                if tree is None:
                    for href in parser.links:
                        parts = urlsplit(urljoin(url, href))
                        if (parts.hostname == urlsplit(root).hostname and not parts.query
                                and parts.scheme in ("http", "https")
                                and Path(parts.path).suffix.lower() in ("", ".htm", ".html")):
                            links.add(urljoin(root, "/" + parts.path.lstrip("/")))
                return url, page, None, links
            except (OSError, ValueError) as exc:
                if attempt:
                    return url, None, str(exc), set()

    pages, errors = [], {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        seen = set()
        while urls:
            batch = sorted(urls - seen)
            if tree is None:
                batch = batch[:max(0, 120 - len(seen))]
            if not batch:
                break
            seen.update(batch)
            urls = set()
            for url, page, error, links in pool.map(download, batch):
                if page:
                    pages.append(page)
                    urls.update(links)
                else:
                    errors[url] = error
    if not pages or not any(p["url"] == root for p in pages):
        raise ValueError("site homepage could not be frozen")
    stamp = snapshot_digest(pages)
    snapshot = {"root": root, "sitemap": sitemap if tree is not None else None, "utc": datetime.now(timezone.utc).isoformat(),
                "sha256": stamp, "pages": pages, "errors": errors}
    write_result(path, snapshot)
    return snapshot


def snapshot_digest(pages):
    return hashlib.sha256(json.dumps(pages, sort_keys=True).encode()).hexdigest()


def site_tools(snapshot, result_limit=8, snippets=False):
    if snapshot_digest(snapshot["pages"]) != snapshot["sha256"]:
        raise ValueError("snapshot content hash mismatch")
    pages = {p["url"]: p for p in snapshot["pages"]}

    def words(text):
        return re.findall(r"\w+", text.casefold())

    counts = {url: Counter(words((p["title"] + " ") * 3 + p["text"])) for url, p in pages.items()}
    lengths = {url: sum(c.values()) for url, c in counts.items()}
    mean_length = sum(lengths.values()) / len(pages)
    doc_freq = Counter(term for c in counts.values() for term in c)

    def search(args):
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("supply search words")
        terms = sorted(set(words(query)))
        hits = []
        for url, c in counts.items():
            score = 0.0
            length_penalty = 1.2 * (0.25 + 0.75 * lengths[url] / mean_length)
            for term in terms:
                if c[term]:
                    freq = doc_freq[term]
                    idf = math.log(1 + (len(pages) - freq + 0.5) / (freq + 0.5))
                    score += idf * c[term] * 2.2 / (c[term] + length_penalty)
            if score:
                hits.append((score, url))
        ranked = sorted(hits, reverse=True)[:result_limit]
        results = []
        for _, url in ranked:
            line = f"{pages[url]['title']} | {url}"
            if snippets:
                body = pages[url]["text"]
                passages = [body[i:i + 240] for i in range(0, len(body), 240)]
                snippet = max(passages, key=lambda s: len(set(terms).intersection(words(s))), default="")
                line += " | " + " ".join(snippet.split())
            results.append(line)
        return "\n".join(results) or "No matches"

    def visit(args):
        url = args.get("url")
        if not isinstance(url, str) or url not in pages:
            raise ValueError("use a URL returned by search or the site root")
        page = pages[url]
        start = args.get("offset", 0)
        if type(start) is not int or not 0 <= start < len(page["text"]):
            raise ValueError("invalid character offset")
        find = args.get("find", "")
        if not isinstance(find, str):
            raise ValueError("find must be text")
        if find:
            match = re.search(re.escape(find), page["text"][start:], re.I)
            if not match:
                return f"{url}: phrase not found"
            start = max(0, start + match.start() - 450)
        end = min(len(page["text"]), start + WINDOW)
        return f"{page['title']} | {url} | chars {start}:{end}/{len(page['text'])}\n" + page["text"][start:end]

    return {
        "search": Tool('{"query":"words"} searches the frozen site. Returns up to eight titles and URLs.'
                       if result_limit == 8 and not snippets else
                       f'{{"query":"words"}} searches the frozen site. Returns up to {result_limit} results.', search),
        "visit": Tool('{"url":"URL","offset":0,"find":"optional literal phrase"} reads a page window. '
                      'Use offset to continue or find to jump to a phrase.', visit),
    }

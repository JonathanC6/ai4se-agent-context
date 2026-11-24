"""论文网页工具的近似实现。Serper 提供 Google 结果，You.com 提供 Markdown。"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from pace.agent import Tool
from pace.providers.api import NoRedirect, ProviderError
from .paper_pilot import extract_page
from .webwalkerqa import ROOT


def credentials():
    path = ROOT / ".local.json"
    local = json.loads(path.read_text()) if path.exists() else {}
    search = os.getenv("SERPER_API_KEY") or local.get("serper_api_key")
    contents = os.getenv("YDC_API_KEY") or local.get("you_api_key")
    missing = [k for k, v in [("SERPER_API_KEY", search), ("YDC_API_KEY", contents)] if not v]
    if missing:
        raise SystemExit("缺少网页服务凭据 " + ", ".join(missing))
    return search, contents


def post(url, key, body):
    req = Request(url, data=json.dumps(body).encode(), headers={"X-API-Key": key, "Content-Type": "application/json"})
    try:
        with build_opener(NoRedirect()).open(req, timeout=90) as response:
            return json.load(response)
    except HTTPError as exc:
        raise ProviderError(f"{urlsplit(url).hostname} HTTP {exc.code}") from None
    except (ValueError, OSError) as exc:
        raise ProviderError(f"{urlsplit(url).hostname} {type(exc).__name__}") from None


def items(value):
    values = value if isinstance(value, list) else [value]
    if not values or not all(isinstance(v, str) and v.strip() for v in values):
        raise ValueError("provide nonempty strings")
    return values


class PaperBrowser:
    def __init__(self, api, keys):
        self.api = api
        self.search_key, self.contents_key = keys

    def search_one(self, query):
        chinese = re.search(r"[\u3400-\u9fff]", query)
        reply = post("https://google.serper.dev/search", self.search_key,
                     dict(q=query, num=10, gl="cn" if chinese else "us", hl="zh-cn" if chinese else "en"))
        if not isinstance(reply, dict) or "organic" not in reply and "searchParameters" not in reply:
            raise ProviderError("invalid Serper response")
        return {"query": query, "results": [
            dict(title=r.get("title", ""), url=r["link"], snippet=r.get("snippet", ""))
            for r in reply.get("organic", [])[:10] if r.get("link")]}

    def search(self, args):
        queries = items(args.get("query"))
        with ThreadPoolExecutor(min(4, len(queries))) as pool:
            return json.dumps(list(pool.map(self.search_one, queries)), ensure_ascii=False)

    def fetch_pages(self, urls):
        return post("https://ydc-index.io/v1/contents", self.contents_key,
                    {"urls": urls, "formats": ["markdown"]})

    def visit(self, args):
        urls = items(args.get("url"))
        goals = items(args.get("goal"))
        if len(goals) == 1:
            goals *= len(urls)
        if len(urls) != len(goals) or any(urlsplit(u).scheme not in ("https", "http") or not urlsplit(u).hostname for u in urls):
            raise ValueError("supply HTTP(S) URLs and a goal for each")
        offset = args.get("offset", 0)
        if type(offset) is not int or offset < 0:
            raise ValueError("invalid character offset")
        reply = self.fetch_pages(urls)
        if not isinstance(reply, list):
            raise ProviderError("invalid You.com response")
        pages = {p["url"]: p.get("markdown") for p in reply if p.get("url")}
        observations = []
        for u, goal in zip(urls, goals):
            page = pages.get(u)
            if not page or offset >= len(page):
                observations.append({"url": u, "read": False, "message": "No text at this URL and offset."})
                continue
            result = extract_page(self.api, u, goal, page, offset, min(len(page), offset + 24000))
            observations.append({"url": u, "read": True, "extraction": result})
        return json.dumps(observations, ensure_ascii=False)

    def tools(self):
        return {
            "search": Tool('{"query":"terms"} searches Google; query can also be a list. Returns up to ten titles, snippets and URLs per query.', self.search),
            "visit": Tool('{"url":"URL","goal":"facts to extract","offset":0} reads webpage Markdown. URL and goal can also be parallel lists. Offset is optional.', self.visit),
        }

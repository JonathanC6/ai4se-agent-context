"""免密钥的 You.com 搜索和正文读取。模型密钥只交给 Labhuan。"""
import json
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pace.agent import Tool
from pace.providers import ProviderError
from .google_you import PaperBrowser


def you_call(name, arguments):
    body = dict(jsonrpc="2.0", id=1, method="tools/call", params=dict(name=name, arguments=arguments))
    request = Request("https://api.you.com/mcp/free", data=json.dumps(body).encode(),
                      headers={"User-Agent": "pace-course/1.0", "Content-Type": "application/json",
                               "Accept": "application/json, text/event-stream"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=60) as response:
                stream = response.read().decode()
            break
        except HTTPError as exc:
            if exc.code not in (429, 502, 503, 504) or attempt == 2:
                raise ProviderError(f"You.com {name}: HTTP {exc.code}") from None
            time.sleep(3 * (attempt + 1))
        except OSError:
            if attempt == 2:
                raise ProviderError(f"You.com {name}: network unavailable") from None
    for line in stream.splitlines():
        if not line.startswith("data:"):
            continue
        event = json.loads(line[5:])
        if "result" in event:
            result = event["result"]
            entry = result["content"][0]["text"]
            if result.get("isError"):
                if re.search("limit|quota|auth|credit", entry, re.I):
                    raise ProviderError("You.com service limit: " + entry[:160])
                raise ValueError(entry[:240])
            return json.loads(entry)
    raise ProviderError("missing You.com response")


class PublicBrowser(PaperBrowser):
    def search_one(self, query):
        suffix = " loc:CN" if re.search(r"[\u3400-\u9fff]", query) else " loc:US"
        data = you_call("you-search", dict(query=query + suffix, count=10, extraction="none"))
        return dict(query=query, results=[dict(url=r["url"], title=r.get("title", ""),
                    snippet=r.get("description", "")) for r in data["results"].get("web", [])[:10]])

    def fetch_pages(self, urls):
        pages = []
        for url in urls:
            data = you_call("you-extract", dict(url=url, formats=["markdown"]))["output"]
            pages.append({"url": url, "markdown": data.get("contents", {}).get("full_page", {}).get("markdown")})
        return pages

    def tools(self):
        tools = super().tools()
        tools["search"] = Tool(tools["search"].description.replace("Google", "You.com"), self.search)
        return tools

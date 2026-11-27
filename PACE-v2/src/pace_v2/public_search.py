"""读取 DuckDuckGo Lite 的自然搜索结果；不保存空的验证页。"""
from html.parser import HTMLParser
from threading import Lock
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

from pace.providers import ProviderError
from .browser import Browser


class ResultParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.field = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag == "a" and "result-link" in classes:
            url = urljoin("https://lite.duckduckgo.com/", attrs.get("href", ""))
            link = urlsplit(url)
            if link.hostname in ("duckduckgo.com","lite.duckduckgo.com") and link.path == "/l/":
                url = parse_qs(link.query).get("uddg", [""])[0]
            self.rows.append(dict(url=url, title="", snippet=""))
            self.field, self.parts = "title", []
        elif tag == "td" and "result-snippet" in classes and self.rows:
            self.field, self.parts = "snippet", []

    def handle_data(self, text):
        if self.field:
            self.parts.append(text)

    def handle_endtag(self, tag):
        if (tag,self.field) in (("a","title"),("td","snippet")):
            self.rows[-1][self.field] = " ".join("".join(self.parts).split())
            self.field, self.parts = None, []


class PublicLiteBrowser(Browser):
    search_provider = "duckduckgo-lite"
    _lock = Lock()
    _last_request = 0.0

    def new_search(self, query):
        url = "https://lite.duckduckgo.com/lite/?" + urlencode({"q":query})
        request = Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with self._lock:
            sleep(max(0, 3 - (monotonic() - PublicLiteBrowser._last_request)))
            PublicLiteBrowser._last_request = monotonic()
            try:
                with urlopen(request, timeout=35) as response:
                    text = response.read(2_000_000).decode("utf-8", "replace")
            except HTTPError as exc:
                raise ProviderError(f"DuckDuckGo search: HTTP {exc.code}") from None
            except OSError as exc:
                raise ProviderError(f"DuckDuckGo search: {type(exc).__name__}") from None
        parser = ResultParser()
        parser.feed(text)
        parser.close()
        if not parser.rows and "no results found for" not in text.lower():
            raise ProviderError("DuckDuckGo search returned no usable results page")
        return dict(query=query, results=parser.rows[:10])

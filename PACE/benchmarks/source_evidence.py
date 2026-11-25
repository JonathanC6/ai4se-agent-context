"""在单题内重读已获取的网页正文，避免历史块只留下第一次提取的结论。"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

from pace.agent import Tool
from .paper_pilot import extract_page


@dataclass(frozen=True)
class Source:
    url: str
    text: str
    digest: str
    start: int


class SourceEvidence:
    def __init__(self, api, directory=None):
        self.api = api
        self.directory = directory
        self.sources = {}
        self.ids = {}
        self.cache = {}

    def remember(self, url, text, offset, end):
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        key = (url, digest, offset)
        if key not in self.ids:
            if self.directory is not None:
                path = Path(self.directory) / f"{digest}.txt"
                if not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    # 每题独立的临时文件，多个工作线程可以保存同一正文。
                    with NamedTemporaryFile(dir=path.parent, delete=False) as f:
                        f.write(text.encode("utf-8"))
                    Path(f.name).replace(path)
            source_id = f"S{len(self.sources) + 1}"
            self.sources[source_id] = Source(url, text, digest, offset)
            self.ids[key] = source_id
        return dict(source_id=self.ids[key], text_sha256=digest, source_chars=len(text),
                    window=[offset, end])

    def reread(self, args):
        sid, goal = args.get("source_id"), args.get("goal")
        if not isinstance(sid, str) or sid not in self.sources:
            raise ValueError("supply a source_id from a successful visit in this episode")
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("supply a specific missing fact as goal")
        src = self.sources[sid]
        start = args.get("offset", src.start)
        if type(start) is not int or not 0 <= start < len(src.text):
            raise ValueError("offset outside source text")
        find = args.get("find")
        if find is not None:
            if not isinstance(find, str) or not find.strip():
                raise ValueError("find must be a nonempty literal phrase")
            # 可在整个快照里定位，包括首次 visit 未进入提取窗口的部分。
            lower = start if "offset" in args else 0
            match = re.compile(re.escape(find), re.IGNORECASE).search(src.text, lower)
            if not match:
                raise ValueError("literal phrase not found; try another phrase or an offset")
            start = max(0, match.start() - 240)
        key = (sid, goal.strip(), start)
        if key not in self.cache:
            end = min(start + 24000, len(src.text))
            extracted = extract_page(self.api, src.url, goal.strip(), src.text, start, end)
            row = dict(source_id=sid, source=src.url, text_sha256=src.digest, window=[start, end],
                       source_chars=len(src.text), excerpt=src.text[start:min(start+800, end)], extraction=extracted)
            self.cache[key] = json.dumps(row, ensure_ascii=False)
        return self.cache[key]

    def tool(self):
        return Tool('{"source_id":"S1","goal":"missing fact","find":"literal phrase","offset":0} '
                    're-extracts from the saved original page when visit omitted a fact. Optional find locates '
                    'a phrase in the full page; optional offset selects the starting character.', self.reread)

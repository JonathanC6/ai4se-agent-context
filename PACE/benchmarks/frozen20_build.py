"""从本次公开搜索的审核清单重建冻结候选。生成时不读取参考答案。"""
import json
import re
from urllib.parse import unquote, urlsplit
from .webwalker_frozen20 import FIXTURE, OUT

STOP = set("the and was what when who why how for did which its with from does that were are their this during about where upon would should will can have had been".split())
BLOCK_URL = re.compile(r"web.?walker|huggingface|webthinker|webdancer|2504\.21776|/datasets?/|hf-mirror|modelscope.cn/datasets", re.I)


def keywords(title, question):
    question = question.casefold()
    kept = []
    for term in re.findall(r"[A-Za-z0-9]+|[\u3400-\u9fff]+", title):
        word = term.casefold()
        present = word in question.split() if term.isascii() else term in question
        if len(term) > 2 and present and word not in STOP and word not in kept:
            kept.append(word)
    return kept[:8]


def build(audit):
    fixture = {}
    for n, row in audit.items():
        docs = []
        seen = set()
        for item in row["results"]:
            url = item["url"]
            if item["blocked"] or url in seen or not urlsplit(url).hostname or BLOCK_URL.search(unquote(url)):
                continue
            seen.add(url)
            docs.append(dict(url=url, keywords=keywords(item["title"], row["query"])))
            if len(docs) == 10:
                break
        fixture[n] = docs
    return fixture


if __name__ == "__main__":
    raw = json.loads((OUT / "source-audit.json").read_text())
    rendered = json.dumps(build(raw), ensure_ascii=False, indent=2) + "\n"
    if FIXTURE.exists() and FIXTURE.read_text() != rendered:
        raise ValueError("refusing to change the frozen search fixture")
    if not FIXTURE.exists():
        FIXTURE.write_text(rendered)

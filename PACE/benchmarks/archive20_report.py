"""在相同已判分题号上比较准确率、标注页覆盖与服务端 token。"""
import json
from collections import Counter

from pace.records import write_result
from .archive_reader import BASE
from .webwalker_tools20 import measurements
from .webwalkerqa import CACHE, ROOT, load_dataset


FLAGS = ("webwalkerqa", "webwalker-qa", "webwalker_qa", "webthinker", "webdancer",
         "huggingface.co/datasets")


def read(folder, n, row):
    path = folder / f"rep-1/react/row-{n}.json"
    if not path.exists():
        return None
    record = json.loads(path.read_text())
    if (record["row"], record["arm"], record["question"]) != (n, "react", row["question"]):
        raise ValueError(f"wrong episode at {path}")
    if type(record.get("grade", {}).get("correct")) is not bool:
        return None
    return record


def observations(record, kind):
    for step in (record or {}).get("history", []):
        raw = step["observation"]
        if step["kind"] == kind and raw.startswith("["):
            yield from json.loads(raw)


def flagged(record):
    return sorted({item["url"] for q in observations(record, "search") for item in q["results"]
                   if any(word in str(item).lower() for word in FLAGS)})


def metrics(record, row):
    if record is None:
        return None
    roles = {k: v["total_tokens"] for k, v in record["usage"].items()}
    return dict(measurements(record, row, True), steps=len(record["steps"]),
                tokens=sum(roles.values()), roles=roles)


def totals(group):
    keys = ("correct", "steps", "tokens", "any_hit", "all_hit", "matched", "references")
    return {k: sum(v[k] for v in group) for k in keys} | {"n": len(group)}


def main():
    old = ROOT / "results/webwalker-tools20-you-public"
    dataset = load_dataset(CACHE)
    cases = {}
    for n in json.loads((BASE / "config.json").read_text())["rows"]:
        row = dataset[n - 1]
        current = read(BASE, n, row)
        if current is None:
            raise ValueError(f"incomplete row {n}")
        previous = read(old, n, row)
        # 仅统计最终已判分轨迹中的动作；用量流水另计中断与重试。
        old_queries = {q["query"] for q in observations(previous, "search")}
        queries = [q["query"] for q in observations(current, "search")]
        search = Counter("old_search" if q in old_queries else "web_search" for q in queries)
        visits = list(observations(current, "visit"))
        cases[n] = dict(
            kind=row["info"]["type"], previous=metrics(previous, row), current=metrics(current, row),
            search_calls=dict(search), pdf_reads=sum(v.get("format") == "pdf" for v in visits),
            archive_requests=sum(bool(v.get("as_of")) for v in visits),
            archive_reads=sum(bool(v.get("as_of")) and v["read"] for v in visits),
            flagged_results=flagged(current), previous_flagged_results=flagged(previous),
        )
    paired = [v for v in cases.values() if v["previous"] is not None]
    summary = dict(paired_old=totals([v["previous"] for v in paired]),
                   paired_new=totals([v["current"] for v in paired]),
                   full_new=totals([v["current"] for v in cases.values()]))
    for folder, key in ((BASE, "billed_tokens"), (old, "previous_billed_tokens")):
        summary[key] = sum(json.loads(l)["total_tokens"] for l in
                           (folder / "usage.jsonl").read_text().splitlines())
    write_result(BASE / "comparison.json", dict(summary=summary, cases=cases))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

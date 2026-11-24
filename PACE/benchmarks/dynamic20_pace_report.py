"""校验同题配置和搜索回包，统计 PACE 与 ReAct 每题的得分、开销和压缩行为。"""
from collections import Counter
import json

from pace.records import write_result
from .archive20_report import metrics, observations, totals
from .webwalker_dynamic20 import OUT, key, exclusion
from .webwalkerqa import load_dataset, CACHE


def summarize(folder, arm, rows, dataset):
    cases, roles, queries = {}, Counter(), Counter()
    for n in rows:
        row = dataset[n-1]
        record = json.loads((folder / f"rep-1/{arm}/row-{n}.json").read_text())
        if (record["question"], record["row"], record["repeat"], record["arm"]) != (row["question"], n, 1, arm):
            raise ValueError(f"wrong episode: {arm} {n}")
        if type(record["grade"]["correct"]) is not bool or record["grade"]["version"] != "legacy-v1":
            raise ValueError(f"ungraded or incompatible grade: {arm} {n}")
        stats = metrics(record, row)
        roles.update(stats["roles"])
        for q in observations(record, "search"):
            digest = key(q["query"])
            cache = json.loads((OUT / "search" / f"{digest}.result.json").read_text())
            if cache["query"] != q["query"] or cache["results"] != q["results"]:
                raise ValueError(f"wrong cache contents: {arm} {n}")
            if any(exclusion(x["url"], x["title"] + " " + x["snippet"]) for x in q["results"]):
                raise ValueError(f"flagged result: {arm} {n}")
            queries[digest] += 1
        compressed = [step["step"] for step in record["steps"]
                      if any(c["shown"] != "FULL" for c in step["chunks"])]
        seen_compressed, restored = set(), set()
        for step in record["steps"]:
            for c in step["chunks"]:
                if c["shown"] != "FULL":
                    seen_compressed.add(c["id"])
                elif c["id"] in seen_compressed:
                    restored.add(c["id"])
        cases[n] = dict(stats, kind=row["info"]["type"], status=record["status"],
                        compressed_steps=compressed, reexpanded_chunk_ids=sorted(restored),
                        glimpse_calls=record["glimpse_calls"],
                        summary_states=dict(Counter(t["summary_state"] for t in record["history"] if "summary_state" in t)))
    ledger = sum(json.loads(l)["total_tokens"] for l in (folder / "usage.jsonl").read_text().splitlines())
    return cases, dict(totals(list(cases.values())), roles=roles, ledger_tokens=ledger,
                       compressed_cases=sum(bool(c["compressed_steps"]) for c in cases.values()),
                       compressed_steps=sum(len(c["compressed_steps"]) for c in cases.values()),
                       glimpse_calls=sum(c["glimpse_calls"] for c in cases.values())), queries


def main():
    folder = OUT.with_name(OUT.name + "-pace")
    config = json.loads((OUT / "config.json").read_text())
    pace_config = json.loads((folder / "config.json").read_text())
    if pace_config != dict(config, arms=["pace"], summary_model=config["model"]):
        raise ValueError("paired configurations differ")
    dataset = load_dataset(CACHE)
    rows = config["rows"]
    if len(set(rows)) != 20 or len(rows) != 20:
        raise ValueError("wrong cohort size")
    react, react_stats, react_queries = summarize(OUT, "react", rows, dataset)
    pace, pace_stats, pace_queries = summarize(folder, "pace", rows, dataset)
    cases = {n: dict(react=react[n], pace=pace[n]) for n in rows}
    searches = dict(pace_total=pace_queries.total(), pace_unique=len(pace_queries),
                    distinct_shared=len(react_queries.keys() & pace_queries.keys()))
    report = dict(summary=dict(react=react_stats, pace=pace_stats), searches=searches, cases=cases)
    write_result(folder / "comparison.json", report)
    print(json.dumps(report["summary"], indent=2), searches)


if __name__ == "__main__":
    main()

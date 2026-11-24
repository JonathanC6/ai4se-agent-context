"""逐条核验动态搜索观察和缓存，比较三批同题的已判分轨迹。"""
from collections import Counter
import json

from pace.records import write_result
from .archive20_report import read, observations, metrics, totals
from .archive_reader import BASE
from .webwalker_dynamic20 import OUT, FROZEN, exclusion, key
from .webwalkerqa import CACHE, load_dataset


def main():
    folders = {"frozen": FROZEN / "archive", "dynamic": OUT, "prior_dynamic": BASE}
    dataset = load_dataset(CACHE)
    config = json.loads((OUT / "config.json").read_text())
    cases, queries = {}, Counter()
    for n in config["rows"]:
        row = dataset[n-1]
        case = {"kind": row["info"]["type"]}
        for group, folder in folders.items():
            r = read(folder, n, row)
            if r is None:
                raise ValueError(f"missing grade in {group} row {n}")
            case[group] = metrics(r, row)
            if group != "dynamic":
                continue
            calls = list(observations(r, "search"))
            for q in calls:
                digest = key(q["query"])
                cached = json.loads((OUT / "search" / f"{digest}.result.json").read_text())
                if q["query"] != cached["query"] or q["results"] != cached["results"]:
                    raise ValueError(f"cache mismatch on row {n}")
                if any(exclusion(i["url"], i["title"]+" "+i["snippet"]) for i in q["results"]):
                    raise ValueError(f"exposed flagged result on row {n}")
                queries[digest] += 1
            visits = list(observations(r, "visit"))
            case.update(status=r["status"], queries=len(calls),
                        search_steps=sum(h["kind"] == "search" for h in r["history"]),
                        pdf_reads=sum(v.get("format") == "pdf" for v in visits),
                        archive_reads=sum(bool(v.get("as_of")) and v["read"] for v in visits))
        cases[n] = case
    summary = {}
    for group, folder in folders.items():
        stats = totals([v[group] for v in cases.values()])
        roles = Counter()
        for c in cases.values():
            roles.update(c[group]["roles"])
        summary[group] = dict(stats, roles=roles, ledger_tokens=sum(
            json.loads(l)["total_tokens"] for l in (folder / "usage.jsonl").read_text().splitlines()))
    removed = [i for k in queries for i in json.loads(
        (OUT / "search" / f"{k}.result.json").read_text())["excluded"]]
    search = dict(served=sum(queries.values()), distinct=len(queries),
                  excluded_entries=len(removed), excluded_urls=len({v["url"] for v in removed}))
    write_result(OUT / "comparison.json", dict(summary=summary, search=search, cases=cases))
    print(json.dumps(dict(summary=summary,search=search),indent=2))


if __name__ == "__main__":
    main()

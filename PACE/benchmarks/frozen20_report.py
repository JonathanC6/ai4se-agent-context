"""核对每条实际搜索观察，并汇总本轮和上轮同题新读取器轨迹。"""
import hashlib
import json
from collections import Counter

from pace.records import write_result
from .archive20_report import metrics, observations, read, totals
from .webwalker_frozen20 import BASE, FIXTURE, OUT, FrozenBrowser
from .webwalkerqa import CACHE, load_dataset


def main():
    folder = OUT / "archive"
    config = json.loads((folder / "config.json").read_text())
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == config["search_sha256"]
    cases = {}
    dataset = load_dataset(CACHE)
    docs = json.loads(FIXTURE.read_text())
    for n in config["rows"]:
        row = dataset[n - 1]
        old, cur = (read(d, n, row) for d in (BASE, folder))
        if old is None or cur is None:
            raise ValueError(f"missing grade on row {n}")
        reference = FrozenBrowser(row["root_url"], None, n, docs[str(n)], "archive", folder)
        calls = [h for h in cur["history"] if h["kind"] == "search"]
        served = [h["observation"] for h in calls if not h["observation"].startswith("Tool error:")]
        if any(raw != reference.search_reply for raw in served):
            raise ValueError(f"non-frozen search response on row {n}")
        visits = list(observations(cur, "visit"))
        cases[n] = dict(kind=row["info"]["type"], previous=metrics(old, row), current=metrics(cur, row),
                        status=cur["status"], candidates=len(reference.cards), searches=len(served),
                        invalid_searches=len(calls)-len(served), visits=len(visits),
                        reads=sum(v["read"] for v in visits),
                        pdf_reads=sum(v.get("format") == "pdf" for v in visits),
                        archive_reads=sum(v["read"] and bool(v.get("as_of")) for v in visits))
    summary = {}
    for k, d in (("current", folder), ("previous", BASE)):
        summary[k] = totals([v[k] for v in cases.values()])
        roles = Counter()
        for row in cases.values():
            roles.update(row[k]["roles"])
        summary[k]["roles"] = roles
        summary[k]["ledger_tokens"] = sum(json.loads(line)["total_tokens"]
                                          for line in (d / "usage.jsonl").read_text().splitlines())
    write_result(OUT / "comparison.json", dict(search_sha256=config["search_sha256"],
                                              summary=summary, cases=cases))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

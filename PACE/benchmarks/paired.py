"""同一题单和站点快照可供不同上下文策略复用。"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pace.records import write_result
from .webwalkerqa import CACHE, CHAT, DATA_SHA, EMBED, REVISION, ROOT, load_dataset, run_case
from .webwalker_snapshot import site_tools


def main(variant="pace", strategy_factory=None, out=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--out", type=Path, default=out or ROOT / "results/paired20")
    parser.add_argument("--plan", type=Path, default=Path(__file__).with_name("paired20.json"))
    parser.add_argument("--only", nargs="+", type=int, help="resume these rows within the same plan")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    rows = load_dataset(CACHE)
    sites = {}
    hashes = {}
    for root, name in plan["snapshots"].items():
        snapshot = json.loads((CACHE / name).read_text())
        if snapshot["root"] != root.replace("http://", "https://"):
            raise ValueError("snapshot root mismatch")
        sites[root] = (snapshot["root"], site_tools(snapshot))
        hashes[root] = snapshot["sha256"]
    config = dict(protocol=3, variant=variant, rows=plan["rows"], snapshots=hashes,
                  dataset_revision=REVISION, dataset_sha256=DATA_SHA,
                  actor=CHAT, summary=CHAT, embedding=EMBED, judge=CHAT,
                  budget=128000, horizon=16, max_steps=16)
    cfg = args.out / "config.json"
    if cfg.exists() and json.loads(cfg.read_text()) != config:
        raise ValueError("output directory contains another configuration")
    write_result(cfg, config)

    def execute(n):
        row = rows[n - 1]
        root, tools = sites[row["root_url"]]
        # 一个题目独占一份策略状态；两组共用浏览和评分实现。
        strategy = strategy_factory() if strategy_factory else None
        result = run_case(n, row, root, tools, config, args.out, strategy)
        print(variant, n, result["grade"]["correct"], len(result["steps"]), flush=True)

    selected = args.only or plan["rows"]
    if not set(selected) <= set(plan["rows"]) or len(selected) != len(set(selected)):
        parser.error("--only must contain unique rows from the plan")
    failures = []
    with ThreadPoolExecutor(args.jobs) as pool:
        jobs = {pool.submit(execute, n): n for n in selected}
        for job in as_completed(jobs):
            try:
                job.result()
            except Exception as exc:
                failures.append(jobs[job])
                print("incomplete", jobs[job], str(exc), flush=True)
    if failures:
        raise SystemExit(f"Retry incomplete rows with the same command: {failures}")


if __name__ == "__main__":
    main()

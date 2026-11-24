"""固定 20 题，从空历史独立运行 ReAct。"""
import argparse
import fcntl
import json
from concurrent.futures import ThreadPoolExecutor
from .archive_reader import ArchiveBrowser, BASE
from .paper_pilot import episode
from .webwalker_full import FullRunAPI
from .webwalker_tools20 import PLAN
from .webwalkerqa import ROOT, CACHE, load_dataset
from pace.records import write_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--cdx", action="store_true", help="enable the CDX fallback in a separate run directory")
    args = parser.parse_args()
    jobs = args.jobs
    if jobs < 1:
        parser.error("jobs must be positive")
    output = BASE.with_name(BASE.name + "-cdx") if args.cdx else BASE
    old = ROOT / "results/webwalker-tools20-you-public"
    cfg = json.loads((old / "config.json").read_text())
    rows = load_dataset(CACHE)
    selected = json.loads(PLAN.read_text())["selected"]
    numbers = sorted(selected["single_source"] + selected["multi_source"])
    assert cfg["rows"] == numbers and len(set(numbers)) == 20
    cfg.update(protocol="archive-pdf-search-cdx-v2" if args.cdx else "archive-pdf-search-v1", arms=["react"])
    cfg.pop("pace_gate", None)
    output.mkdir(exist_ok=True, parents=True)
    with (output / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = output / "config.json"
        if path.exists() and json.loads(path.read_text()) != cfg:
            raise ValueError("different protocol in output directory")
        write_result(path, cfg)
        def one(n):
            job = (1, n, "react")
            def api_factory():
                api = FullRunAPI.configured()
                api.job, api.output = job, output
                return api
            record = old / f"rep-1/react/row-{n}.json"
            print(episode(job, cfg, rows, None, None, output, api_factory=api_factory,
                          browser=lambda root, api: ArchiveBrowser(api, n, record, use_cdx=args.cdx, output=output).tools()), flush=True)
        with ThreadPoolExecutor(jobs) as pool:
            list(pool.map(one, numbers))


if __name__ == "__main__":
    main()

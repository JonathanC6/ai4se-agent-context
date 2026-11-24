"""固定 16K 预算对照；三组共用查询缓存和本机编码器。"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json

from .paper_pilot import DenseEncoder
from .webwalker_dynamic20 import OUT, DynamicBrowser, run_cohort
from .webwalkerqa import load_dataset, CACHE

BUDGET = 16000
BASE = OUT.with_name("webwalker-budget20")
GROUPS = ("react", "pace", "pace-guided")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", nargs="+", choices=(*GROUPS, "pace-quadratic", "pace-occupancy"), default=GROUPS)
    parser.add_argument("--rows", nargs="+", type=int, help="subset of the fixed cohort, in a separate result folder")
    parser.add_argument("--jobs", type=int, default=3, help="每组并行题数")
    args = parser.parse_args()
    rows = load_dataset(CACHE)
    encoder = DenseEncoder() if any(g != "react" for g in args.groups) else None

    def one(group):
        arm = "react" if group == "react" else "pace"
        previous = OUT if arm == "react" else OUT.with_name(OUT.name + "-pace")
        config = json.loads((previous / "config.json").read_text())
        config["budget"] = BUDGET
        if group == "pace-quadratic":
            config["pressure_power"] = 2.0
        if group == "pace-occupancy":
            config["pressure_mode"] = "occupancy"
        if group == "pace-guided":
            config.update(glimpse_limit=1, guided_glimpse=True)
        folder = BASE / group
        if args.rows:
            selected = sorted(set(args.rows))
            if not set(selected).issubset(config["rows"]):
                raise ValueError("requested rows outside the fixed cohort")
            config["rows"] = selected
            folder = folder / ("rows-" + "-".join(map(str, selected)))
        folder.mkdir(exist_ok=True, parents=True)

        def browser(root, api, n):
            return DynamicBrowser(root, api, n, folder)

        run_cohort(rows, config, folder, args.jobs, browser, encoder=encoder if arm == "pace" else None)

    with ThreadPoolExecutor(len(args.groups)) as pool:
        list(pool.map(one, args.groups))


if __name__ == "__main__":
    main()

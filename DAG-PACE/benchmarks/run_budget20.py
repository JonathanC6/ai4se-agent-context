"""复用标准 PACE 的 16K 配置，仅替换为完整依赖策略。"""
import argparse
import json
from pathlib import Path

from benchmarks.paper_pilot import DenseEncoder
from benchmarks.webwalker_budget20 import BASE
from benchmarks.webwalker_dynamic20 import DynamicBrowser, run_cohort
from benchmarks.webwalkerqa import CACHE, load_dataset
from dag_pace.strategy import DependencyStrategy

OUT = Path(__file__).resolve().parents[1] / "results/webwalker-budget20"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    config = json.loads((BASE / "pace/config.json").read_text())
    config["arms"] = ["dag-pace"]
    OUT.mkdir(parents=True, exist_ok=True)

    def browser(root, api, n):
        return DynamicBrowser(root, api, n, OUT)

    run_cohort(load_dataset(CACHE), config, OUT, args.jobs, browser,
               encoder=DenseEncoder(), strategy_factory=DependencyStrategy)


if __name__ == "__main__":
    main()

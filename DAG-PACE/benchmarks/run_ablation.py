"""在两个独立输出目录中续跑四组，第一批 A/D 直接读取原记录。"""
import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parents[2] / "PACE"
DAG = BASE.parent / "DAG-PACE"


def run(cohort, jobs, only=None):
    plan = BASE / f"benchmarks/{cohort}.json"
    wave = "first20" if cohort == "paired20" else cohort
    commands = [
        (["-m", "benchmarks.paired"], BASE / f"results/{cohort}"),
        ([DAG / "benchmarks/ablate.py", "dag"], DAG / f"results/dag/{wave}"),
        ([DAG / "benchmarks/ablate.py", "dag-anchor"], DAG / f"results/dag-anchor/{wave}"),
        ([DAG / "benchmarks/run_paired.py"], DAG / f"results/{cohort}"),
    ]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, [BASE, BASE / "src", DAG / "src"])))

    def execute(item):
        entry, out = item
        out.mkdir(parents=True, exist_ok=True)
        with (out / "run.log").open("a") as log:
            rc = subprocess.run([sys.executable, "-B", *entry, "--plan", plan, "--jobs", str(jobs),
                                 "--out", out, *(["--only", *map(str, only)] if only else [])], stdout=log, stderr=subprocess.STDOUT, env=env).returncode
        print(out, rc, flush=True)
        return rc

    with ThreadPoolExecutor(4) as pool:
        if any(list(pool.map(execute, commands))):
            raise SystemExit("One or more groups incomplete; see run.log and resume.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("cohort", choices=["paired20", "additional20"])
    parser.add_argument("--jobs", type=int, default=4, help="parallel questions per group")
    parser.add_argument("--only", nargs="+", type=int)
    args = parser.parse_args()
    run(args.cohort, args.jobs, args.only)

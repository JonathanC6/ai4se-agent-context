"""直接读取旧轨迹与第二批结果，校验每一批的题单和配置。"""
import json
from pathlib import Path

from benchmarks.webwalkerqa import ROOT

PROJECT = ROOT.parent / "DAG-PACE"
AUDIT = PROJECT / "results/ablation-audit"
PLANS = ("paired20", "additional20")
LABELS = "ABCD"


def read(path):
    return json.loads(path.read_text())


def cohorts():
    seen = set()
    for index, name in enumerate(PLANS):
        plan = read(ROOT / f"benchmarks/{name}.json")
        if len(set(plan["rows"])) != 20 or seen.intersection(plan["rows"]):
            raise ValueError("expected two disjoint 20-item cohorts")
        seen.update(plan["rows"])
        wave = "additional20" if index else "first20"
        dirs = [ROOT / f"results/{name}", PROJECT / f"results/dag/{wave}",
                PROJECT / f"results/dag-anchor/{wave}", PROJECT / f"results/{name}"]
        config = None
        for path, variant in zip(dirs, ("pace", "dag", "dag-anchor", "dag-pace")):
            cfg = read(path / "config.json")
            if cfg.pop("variant") != variant or cfg["rows"] != plan["rows"] or (config and config != cfg):
                raise ValueError(f"incompatible configuration: {path}")
            config = cfg
        for n in plan["rows"]:
            yield n, plan, [p / f"row-{n}.json" for p in dirs]


def token_count(result):
    return sum(role["total_tokens"] for role in result["usage"].values())

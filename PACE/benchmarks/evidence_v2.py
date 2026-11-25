"""复用已评分的 20 题对照配置，仅运行新版 PACE。"""
import argparse
import json
from pathlib import Path

from pace.policy import p95
from .grading import LEGACY
from .paper_pilot import DenseEncoder, ENCODER
from .research_browser import ResearchBrowser, browser_settings
from .webwalker_frozen20 import run_cohort
from .webwalkerqa import CACHE, CHAT, DATA_SHA, ROOT, load_dataset

COHORT = (1, 2, 9, 15, 20, 21, 24, 25, 26, 27, 30, 33, 39, 40, 47, 48, 59, 115, 157, 407)
CONTROL = ROOT / "results/webwalker-window-study-matched20/react/config.json"
OUT = ROOT / "results/webwalker-evidence-v2"
OBSERVE_OUT = OUT.with_name(OUT.name + "-observe")
REVIEWED_OUT = OUT.with_name(OUT.name + "-reviewed")


def configuration(observe_gateway=False):
    old = json.loads(Path(__file__).with_name("evidence_v2_control.json").read_text())
    if CONTROL.exists() and json.loads(CONTROL.read_text()) != old:
        raise ValueError("local ReAct configuration differs from the archived control")
    expected = dict(arms=["react"], rows=list(COHORT), sha256=DATA_SHA, model=CHAT, encoder=ENCODER,
                    grading_version=LEGACY, max_steps=24, budget=6000, provider_input_budget=80000,
                    temperature=0, **browser_settings())
    if any(old.get(k) != value for k, value in expected.items()):
        raise ValueError("ReAct control or active browser differs from the matched cohort")
    calibration = json.loads(Path(__file__).with_name("evidence_v2_horizon.json").read_text())
    lengths = {int(k): v for k, v in calibration["observed_steps"].items()}
    if set(lengths).intersection(COHORT):
        raise ValueError("calibration overlaps evaluation")
    horizon = p95(list(lengths.values()))
    if any(lengths[n] <= horizon for n in calibration["right_censored"]):
        raise ValueError("censoring prevents direct estimation of the horizon")
    if observe_gateway:
        old["enforce_provider_budget"] = False
    return dict(old, arms=["pace"], workload="matched20-evidence-v2", method="evidence-v2", horizon=horizon,
                pressure_mode="evidence-v2", compression_start_ratio=0.90, guided_glimpse=True,
                summary_model=CHAT, coverage_model=CHAT, horizon_observations=len(lengths),
                tools=["search", "visit", "reread", "glimpse", "finish"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=5)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--observe-gateway", action="store_true", help="记录单次网关用量，超过参考线也继续执行")
    parser.add_argument("--reviewed-actor", action="store_true", help="动作启用 JSON 模式，提交前核查压缩网页块")
    parser.add_argument("--rows", nargs="+", type=int, choices=COHORT)
    args = parser.parse_args()
    if args.jobs < 1 or (args.rows and len(set(args.rows)) != len(args.rows)):
        parser.error("choose positive concurrency and distinct rows")
    config = configuration(args.observe_gateway or args.reviewed_actor)
    if args.reviewed_actor:
        config["action_protocol"] = "reviewed-json-v1"
    args.out = args.out or (REVIEWED_OUT if args.reviewed_actor else OBSERVE_OUT if args.observe_gateway else OUT)
    args.out.mkdir(parents=True, exist_ok=True)
    run_cohort(load_dataset(CACHE), config, args.out, args.jobs,
               lambda root, api, n: ResearchBrowser(root, api, n, args.out, rank_rereads=True),
               encoder=DenseEncoder(), selected_rows=args.rows)


if __name__ == "__main__":
    main()

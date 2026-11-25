"""在固定 WebWalkerQA 题单上比较三个 agent，保留每次请求用量和可续跑的逐题轨迹。"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from statistics import median

from pace.records import write_result
from .archive20_report import metrics
from .grading import LEGACY
from .paper_pilot import DenseEncoder, ENCODER
from .webwalker_frozen20 import run_cohort
from .webwalkerqa import CACHE, CHAT, DATA_SHA, REVISION, ROOT, load_dataset

OUT = ROOT / "results/webwalker-research20-v2"
ARMS = ("react", "pace", "dag-pace")


def read(path):
    return json.loads(path.read_text())


def cohort(dataset):
    selected = read(ROOT / "benchmarks/webwalker_tools20.json")["selected"]
    for kind, indices in selected.items():
        if len(indices) != 10 or any(dataset[n - 1]["info"]["type"] != kind for n in indices):
            raise ValueError(f"invalid {kind} cohort")
    rows = sorted(selected["single_source"] + selected["multi_source"])
    if len(set(rows)) != 20:
        raise ValueError("expected 20 distinct paired rows")
    return rows


def budget_audit(record, config):
    """核验每个已执行动作都通过同一 16K 规则，包括最后的提交。"""
    budget = config["budget"]
    steps = record["steps"]
    if len(steps) > config["max_steps"] or record["input_count_method"] != config["token_counter"]:
        raise ValueError("wrong decision limit or counter")
    errors = []
    rejected = []
    for step in steps:
        estimate, actual = step["input_tokens_estimate"], step["input_tokens_actual"]
        if (type(actual) is not int or actual < 1 or estimate > budget or
                step["input_count_error"] != estimate - actual):
            raise ValueError("inconsistent input usage")
        errors.append(estimate - actual)
        if actual > budget:
            rejected.append(step["step"])
    counts = Counter()
    if rejected:
        if (rejected != [len(steps)] or len(record["history"]) != len(steps) - 1
                or record["status"] != "budget_exceeded" or record["answer"] is not None):
            raise ValueError("an action exceeding the provider budget was executed")
        counts["provider_stops"] = 1
        counts["blocked_finish"] = int(steps[-1]["action"].get("tool") == "finish")
    elif record["status"] == "budget_exceeded":
        counts["preflight_stops"] = 1
    return counts, errors


def report(dataset, rows, output=OUT):
    groups, cases = {}, {}
    shared = None
    for arm in ARMS:
        folder = output / arm
        config = read(folder / "config.json")
        if config.pop("arms") != [arm] or config["rows"] != rows:
            raise ValueError("unexpected arm or workload")
        if shared is not None and config != shared:
            raise ValueError("tools, models or budgets differ between groups")
        shared = config
        total = Counter()
        by_type, roles = Counter(), Counter()
        input_errors = []
        for n in rows:
            r = read(folder / f"rep-1/{arm}/row-{n}.json")
            row = dataset[n-1]
            if (r["row"], r["repeat"], r["arm"], r["question"], r["grade"]["version"]) != (
                    n, 1, arm, row["question"], LEGACY):
                raise ValueError(f"wrong episode: {arm} {n}")
            if type(r["grade"]["correct"]) is not bool or (r["status"] != "finished" and r["grade"]["correct"]):
                raise ValueError(f"invalid grade: {arm} {n}")
            m = metrics(r, row)
            stops, errors = budget_audit(r, config)
            total.update(stops)
            input_errors.extend(errors)
            recovery_calls = Counter()
            for turn in r["history"]:
                if turn["kind"] in ("glimpse", "reread"):
                    recovery_calls[turn["kind"]] += 1
            total.update(recovery_calls)
            total.update({k: m[k] for k in ("correct", "steps", "tokens", "any_hit", "all_hit")})
            total[r["status"]] += 1
            roles.update(m["roles"])
            by_type[row["info"]["type"]] += m["correct"]
            cases.setdefault(n, {})[arm] = dict(m, status=r["status"], recovery_calls=recovery_calls,
                                                budget_stops=stops)
        ledger = sum(json.loads(line)["total_tokens"] for line in (folder / "usage.jsonl").read_text().splitlines())
        if ledger < total["tokens"] or sum(roles.values()) != total["tokens"]:
            raise ValueError("token ledger mismatch")
        groups[arm] = dict(total, correct_by_type=by_type, usage=roles, ledger_tokens=ledger,
                           median_absolute_input_error=median(map(abs, input_errors)))
    write_result(output / "comparison.json", dict(config=shared, groups=groups, cases=cases))
    print(json.dumps(groups, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "report"))
    parser.add_argument("--jobs", type=int, default=3, help="每组同时运行的题数")
    parser.add_argument("--arms", choices=ARMS, nargs="+", default=ARMS)
    parser.add_argument("--rows", type=int, nargs="+", help="只运行固定题单中指定的题，报告仍需凑齐 20 题")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    dataset = load_dataset(CACHE)
    rows = cohort(dataset)
    if args.command == "report":
        report(dataset, rows, args.out)
        return
    from .research_browser import ResearchBrowser, browser_settings
    from dag_pace.strategy import DependencyStrategy

    if args.jobs < 1 or len(set(args.arms)) != len(args.arms):
        parser.error("invalid jobs or duplicate arm")
    if args.rows and (len(args.rows) != len(set(args.rows)) or set(args.rows) - set(rows)):
        parser.error("rows must be distinct members of the fixed cohort")
    config = dict(dataset=REVISION, sha256=DATA_SHA, rows=rows, model=CHAT, summary_model=CHAT,
                  encoder=ENCODER, temperature=0, max_steps=24, horizon=16, budget=16000,
                  workload="evidence-budget-v1", grading_version=LEGACY,
                  token_counter="labhuan-calibrated-v1", actor_budget_protocol="per-response-v2",
                  **browser_settings())
    encoder = DenseEncoder() if any(arm != "react" for arm in args.arms) else None

    def run_arm(arm):
        folder = args.out / arm
        folder.mkdir(parents=True, exist_ok=True)

        def browser(root, api, n):
            return ResearchBrowser(root, api, n, folder)

        settings = dict(config, arms=[arm])
        saved = folder / "config.json"
        if saved.exists() and "actor_budget_protocol" not in read(saved):
            # 早期输出按原规则续跑；独立审计另外计算逐响应硬上限。
            del settings["actor_budget_protocol"]
        run_cohort(dataset, settings, folder, args.jobs, browser,
                   encoder=encoder if arm != "react" else None,
                   strategy_factory=DependencyStrategy if arm == "dag-pace" else None,
                   selected_rows=args.rows)

    with ThreadPoolExecutor(len(args.arms)) as pool:
        list(pool.map(run_arm, args.arms))


if __name__ == "__main__":
    main()

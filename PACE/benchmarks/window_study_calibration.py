"""从上一轮有效的 60 条轨迹估算窗口触发率与网关超限次数。全程离线。"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import median

from dag_pace.strategy import DependencyStrategy
from pace.agent import instructions
from pace.memory import Turn
from pace.providers.encoding import VisibleWindowCounter, load_count_tokenizer
from pace.records import write_result
from .paper_pilot import ASSETS, question_prompt
from .research_browser import ResearchBrowser
from .research_budget_audit import audit_episode
from .verified_research20 import ARMS, ORIGINAL, STRICT, compare, ledger, read
from .webwalkerqa import CACHE, load_dataset


def full_sizes(record, steps, question, system, counter):
    """还原每步的系统、题目与全部活跃块全文。DAG 已替代的块不占空间。"""
    blocks = {}
    for i, item in enumerate(record["history"], 1):
        turn = Turn(item["thought"], item["action"], item["observation"], item["kind"])
        blocks[i] = f"[C{i} {turn.kind} full]\n{turn.text()}"
    sizes = []
    for step in record["steps"][:steps]:
        parts = [question, *(blocks[c["id"]] for c in step["chunks"])]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(parts)}]
        sizes.append(counter.messages(messages))
    return sizes


def calibration(original=ORIGINAL, strict=STRICT, visible_budgets=(6000, 8000, 16000, 80000),
                gateway_limits=(16000, 32000, 64000, 72000, 80000, 96000, 128000)):
    # 筛选只使用先前完成的请求与历史长度，不读取新实验的答案或判分。
    dataset = load_dataset(CACHE)
    verified = compare(dataset, original, strict)
    if any(verified["pending"].values()):
        raise ValueError(f"incomplete calibration cohort: {verified['pending']}")
    config = verified["config"]
    counter = VisibleWindowCounter(load_count_tokenizer(ASSETS / "tokenizer.json"))
    full = defaultdict(list)
    requests = []
    for arm in ARMS:
        for label, root in (("original-replay", original), ("strict-live", strict)):
            by_question, _ = ledger(root, arm)
            for case in verified["rows"]:
                if (case["arm"], case["source"]) != (arm, label):
                    continue
                n = case["row"]
                row = dataset[n - 1]
                record = read(root / arm / f"rep-1/{arm}/row-{n}.json")
                audit = audit_episode(record, by_question[n], config["budget"])
                # 正常停止保留该步的格式重试，网关停止只保留到首次超限响应。
                for attempt in audit["attempts"]:
                    if attempt["step"] > case["steps"]:
                        break
                    requests.append(attempt["prompt_tokens"])
                    if attempt["prompt_tokens"] > config["budget"]:
                        break
                tools = ResearchBrowser(row["root_url"], None, n, root / arm).tools()
                glimpse = 0 if arm == "react" else config.get("glimpse_limit", 3)
                system = instructions(tools, glimpse, config.get("guided_glimpse", False))
                if arm == "dag-pace":
                    system += "\n" + DependencyStrategy().instructions
                question = question_prompt(row["root_url"], row["question"])
                full[arm].append(full_sizes(record, case["steps"], question, system, counter))

    peaks = {arm: [max(sizes, default=0) for sizes in episodes] for arm, episodes in full.items()}
    return {
        "questions_per_arm": {arm: len(values) for arm, values in peaks.items()},
        "actor_responses": len(requests),
        "gateway_over_limit": {cap: sum(used > cap for used in requests) for cap in gateway_limits},
        "visible_full_prompt_peaks": {
            arm: dict(median=median(values), maximum=max(values)) for arm, values in peaks.items()
        },
        "episodes_reaching_threshold": {
            budget: {pct: {arm: sum(100 * used >= pct * budget for used in values)
                           for arm, values in peaks.items()} for pct in (80, 90)}
            for budget in visible_budgets
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, default=ORIGINAL)
    parser.add_argument("--strict", type=Path, default=STRICT)
    parser.add_argument("--out", type=Path, help="可选的 JSON 输出路径")
    args = parser.parse_args()
    result = calibration(args.original, args.strict)
    if args.out:
        write_result(args.out, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

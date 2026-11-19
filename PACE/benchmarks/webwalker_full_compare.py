"""汇总首轮配对结果。缺任一判分时不生成全量报告。"""
from collections import Counter
import json
from pathlib import Path

from .full_webwalker_preflight import OUT
from .webwalkerqa import CACHE, ROOT, load_dataset

ARMS = ("react", "pace")


def compact(record):
    history = record["history"]
    visits = [t["observation"] for t in history if t["kind"] == "visit"]
    usage = record["usage"].values()
    return {
        "correct": record["grade"]["correct"],
        "status": record["status"],
        "steps": len(record["steps"]),
        "evidence": any(" chars " in v and "\nDiscovered links:" in v and
                        not v.startswith("Tool error:") for v in visits),
        "tool_error": any(t["observation"].startswith("Tool error:") for t in history),
        "compressed": any(c["shown"] != "FULL" for s in record["steps"] for c in s["chunks"]),
        "glimpse": record["glimpse_calls"],
        "input": sum(v["prompt_tokens"] for v in usage),
        "output": sum(v["completion_tokens"] for v in usage),
        "tokens": sum(v["total_tokens"] for v in usage),
        "actor_tokens": record["usage"]["actor"]["total_tokens"],
        "seconds": record["solver_seconds"] + record["judge_seconds"],
    }


def main():
    config = json.loads((OUT / "config.json").read_text())
    dataset = load_dataset(CACHE)
    cases = []
    totals = {a:Counter() for a in ARMS}
    wins = Counter()
    for n, row in enumerate(dataset, 1):
        pair = {"row":n, "kind":row["info"]["type"], "question":row["question"]}
        for arm in ARMS:
            path = OUT / f"rep-1/{arm}/row-{n}.json"
            if not path.exists():
                raise SystemExit(f"等待 {arm} 第 {n} 题，尚无全量结果")
            record = json.loads(path.read_text())
            if ("grade" not in record or type(record["grade"]["correct"]) is not bool or
                    (record["row"], record["repeat"], record["arm"], record["question"]) !=
                    (n, 1, arm, row["question"])):
                raise ValueError(f"判分缺失或题目身份不符 {path}")
            data = compact(record)
            pair[arm] = data
            stats = totals[arm]
            stats.update({k:v for k,v in data.items() if k != "status"})
            stats[pair["kind"]] += data["correct"]
            stats["limit"] += data["status"] != "finished"
        wins[pair["react"]["correct"],pair["pace"]["correct"]] += 1
        cases.append(pair)
    if len(cases) != 680:
        raise ValueError("unexpected dataset length")
    (OUT / "paired-round1.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in cases))
    lines = ["# WebWalkerQA 完整 main 单轮配对结果", "",
             f"两组使用 {config['model']}，逐题独立运行和判分。单源、多源各 340 题，每题每组最多 {config['max_steps']} 步。",
             "", "| 方法 | 答对 / 680 | 准确率 | 单源 / 340 | 多源 / 340 | 仅本组答对 |",
             "|---|---:|---:|---:|---:|---:|"]
    names = {"pace":"PACE","react":"ReAct"}
    for arm in ARMS:
        s = totals[arm]
        only = wins[True,False] if arm == "react" else wins[False,True]
        lines.append(f"| {names[arm]} | {s['correct']} | {s['correct']/680:.2%} | {s['single_source']} | {s['multi_source']} | {only} |")
    delta = (totals["pace"]["correct"] - totals["react"]["correct"]) / 680 * 100
    lines += ["",f"两组均答对 {wins[True,True]} 题，均答错 {wins[False,False]} 题。PACE 的准确率差为 {delta:+.2f} 个百分点。",
              "", "| 方法 | 平均步数 | 每题平均秒数 | 至少一次返回网页提取结果 | 遇到工具错误的题 | 未正常 finish | 展示过压缩块的题 | glimpse 次数 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for arm,s in totals.items():
        lines.append(f"| {names[arm]} | {s['steps']/680:.2f} | {s['seconds']/680:.1f} | {s['evidence']} | {s['tool_error']} | {s['limit']} | {s['compressed']} | {s['glimpse']} |")
    lines += ["", "| 方法 | 输入 token | 输出 token | 动作模型 token | 全部 token | 估算费用 |",
              "|---|---:|---:|---:|---:|---:|"]
    for arm,s in totals.items():
        cost = (s["input"] * 1.5067674292 + s["output"] * 7.5338371461) / 1e6
        lines.append(f"| {names[arm]} | {s['input']:,} | {s['output']:,} | {s['actor_tokens']:,} | {s['tokens']:,} | ¥{cost:.2f} |")
    lines += ["", "费用根据已保存轨迹的服务端使用量和试跑所用费率估算，未计入没有留下完整轨迹的失败尝试。网页提取成功只表示收到页面提取结果，工具返回错误也可能来自参数或网址选择。",
              "", "本次搜索对入口及已访问页面发现的站内链接排序。两组共用成功页面缓存。论文使用 Google 搜索与 You.com 网页工具，并报告三轮均值。动作、网页提取、PACE 历史摘要与裁判在本次均使用 Sonnet 4.6。",
              "", "[逐题配对记录](../results/webwalkerqa-full/paired-round1.jsonl) · [运行配置](../results/webwalkerqa-full/config.json) · [论文表 1 和附录 E](https://aclanthology.org/2026.acl-long.1252.pdf)"]
    (ROOT / "experiments/webwalkerqa-full-round1.md").write_text("\n".join(lines)+"\n")


if __name__ == "__main__":
    main()

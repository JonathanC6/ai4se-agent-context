"""从冻结的题单和两臂全部评分记录生成试跑结果。"""
from collections import Counter
import json
from statistics import mean

from .paper_pilot import OUT, ROOT
from .webwalkerqa import CACHE, load_dataset


def read(path):
    return json.loads(path.read_text())


def main():
    config = read(OUT / "config.json")
    rows = config["rows"]
    dataset = load_dataset(CACHE)
    arms = ("react", "pace")
    series = {a: [] for a in arms}
    by_row = {i: {} for i in rows}
    for rep in range(1, config["repeats"] + 1):
        for arm in arms:
            cases = []
            for n in rows:
                r = read(OUT / f"rep-{rep}/{arm}/row-{n}.json")
                if ((r["row"], r["arm"], r["repeat"]) != (n, arm, rep)
                        or type(r["grade"]["correct"]) is not bool):
                    raise ValueError("invalid pilot record")
                cases.append(r)
                by_row[n][arm, rep] = r
            series[arm].append(cases)
    lines = ["# Sonnet 4.6 · WebWalkerQA 近似对照", "",
             "[论文配置与本机差异](webwalkerqa-paper-check.md) · [题单与运行配置](../results/paper-pilot/config.json)", "",
             "| 方法 | 第一轮 | 第二轮 | 第三轮 | 三轮平均 | 论文表 1 |",
             "|---|---:|---:|---:|---:|---:|"]
    totals = {}
    for arm in arms:
        scores = [sum(c["grade"]["correct"] for c in cases) for cases in series[arm]]
        totals[arm] = sum(scores) / (len(rows) * len(scores))
        formatted = " | ".join(f"{s}/{len(rows)}" for s in scores)
        paper = "57.9%" if arm == "react" else "65.8%"
        lines.append(f"| {arm.upper()} | {formatted} | {totals[arm]:.1%} | {paper} |")
    gap = (totals["pace"] - totals["react"]) * 100
    lines += ["", f"本次 PACE 相对 ReAct 的准确率差为 {gap:+.1f} 个百分点。论文为 +7.9 个百分点。"
              "两份数据的样本、服务和运行环境不同，单次试跑无法判断统计等效。", "",
              "## 逐题记录", "", "1 表示判对，0 表示判错，顺序为三个轮次。", "",
              "| 主测试集行号 | 类型 | 问题 | ReAct | PACE |", "|---:|---|---|---|---|"]
    for n, entries in by_row.items():
        row = dataset[n - 1]
        strings = [" / ".join(str(int(entries[arm,rep]["grade"]["correct"]))
                              for rep in (1, 2, 3)) for arm in arms]
        lines.append(f"| {n} | {row['info']['type']} | {row['question']} | {strings[0]} | {strings[1]} |")
    lines += ["", "## 运行用量", "", "token 来自远程服务回包，包含目标网页提取。量化 BGE-M3 在本机执行。", "",
              "| 方法 | 平均步数 | 展示过摘要或占位符的轨迹 | glimpse | 动作 | 提取网页 | 历史摘要 | 裁判 | 合计 token | 估算费用 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for arm in arms:
        cases = [r for rep in series[arm] for r in rep]
        usage = Counter()
        cost = 0.
        for case in cases:
            for role, v in case["usage"].items():
                usage[role] += v["total_tokens"]
                cost += (v["prompt_tokens"] * 1.5067674292 + v["completion_tokens"] * 7.5338371461) / 1e6
        compressed = sum(any(chunk["shown"] != "FULL" for step in r["steps"]
                             for chunk in step["chunks"]) for r in cases)
        glimpses = sum(r["glimpse_calls"] for r in cases)
        lines.append(f"| {arm.upper()} | {mean(len(r['steps']) for r in cases):.2f} | {compressed}/{len(cases)} | "
                     f"{glimpses} | {usage['actor']:,} | {usage['visit']:,} | {usage['summary']:,} | {usage['judge']:,} | "
                     f"{sum(usage.values()):,} | ¥{cost:.2f} |")
    lines += ["", "费用按本地保存的 Labhuan 默认分组、未命中缓存的公开费率估算。逐题输出、观察与评分理由保存于本机结果目录。"
              "[模型倍率](https://api.labhuan.com/api/pricing) · [计价单位](https://api.labhuan.com/api/status)"]
    (ROOT / "experiments/webwalkerqa-paper-pilot.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()

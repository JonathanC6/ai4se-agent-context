"""汇总 PACE 在完整 WebWalkerQA main 上的一轮结果与重试用量。"""
from collections import Counter, defaultdict
import json
from statistics import median

from .full_webwalker_preflight import OUT
from .webwalker_full_compare import compact
from .webwalkerqa import CACHE, ROOT, load_dataset

TOKEN_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens")


def cost(usage):
    return (usage["prompt_tokens"] * 1.5067674292 + usage["completion_tokens"] * 7.5338371461) / 1e6


def costs_by_role(saved, journal):
    # 部分早期轨迹没有流水。按题号、角色分别合并，避免重复计算成功请求。
    result = defaultdict(Counter)
    for row, role in saved.keys() | journal.keys():
        key = row, role
        for field in TOKEN_FIELDS:
            result[role][field] += max(saved.get(key, {}).get(field, 0),
                                       journal.get(key, {}).get(field, 0))
    return result


def main():
    dataset = load_dataset(CACHE)
    saved, journal = {}, defaultdict(Counter)
    counts = Counter()
    times = []
    by_type = defaultdict(Counter)
    by_visit = defaultdict(Counter)
    data = []
    for n, row in enumerate(dataset, 1):
        path = OUT / f"rep-1/pace/row-{n}.json"
        if not path.exists():
            raise SystemExit(f"第 {n} 题尚无结果")
        r = json.loads(path.read_text())
        if ((r["arm"], r["repeat"], r["row"], r["question"]) != ("pace", 1, n, row["question"])
                or type(r.get("grade", {}).get("correct")) is not bool):
            raise ValueError(f"判分缺失或题号不符 {path}")
        c = compact(r)
        kind = row["info"]["type"]
        data.append({"row":n, "type":kind, "question":row["question"], "answer":r["answer"],
                     "reason":r["grade"].get("reason"), **c})
        counts.update({k:v for k,v in c.items() if k not in ("status", "seconds")})
        counts[c["status"]] += 1
        for bucket in (by_type[kind], by_visit[c["evidence"]]):
            bucket.update(n=1, correct=c["correct"])
        times.append(c["seconds"])
        for role,usage in r["usage"].items():
            saved[n,role] = usage
    if len(data) != 680:
        raise ValueError("expected 680 rows")
    with (OUT / "usage.jsonl").open() as f:
        for line in f:
            receipt = json.loads(line)
            rep,n,arm = receipt["job"]
            if (rep,arm) == (1,"pace"):
                journal[n,receipt["role"]].update({k:receipt[k] for k in TOKEN_FIELDS})
    bill = costs_by_role(saved, journal)
    total = sum(bill.values(), Counter())
    (OUT / "pace-round1.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in data))
    lines = ["# PACE 在 WebWalkerQA 完整 main 上的单轮结果", "",
             f"PACE 答对 **{counts['correct']}/680（{counts['correct']/680:.2%}）**。论文的 Claude-4-Sonnet 行报告三轮均值 65.8%。",
             "", "| 题目 | 答对 | 分母 | 准确率 |", "|---|---:|---:|---:|"]
    for key,label in [("single_source","单源"),("multi_source","多源")]:
        v = by_type[key]
        lines.append(f"| {label} | {v['correct']} | {v['n']} | {v['correct']/v['n']:.2%} |")
    lines += ["", f"平均 {counts['steps']/680:.1f} 步，单题耗时中位数 {median(times):.0f} 秒。"
              f"共 {counts['step_limit']} 题用尽步数，{counts['budget_exceeded']} 题超出上下文预算。"
              f"{counts['compressed']} 题展示过压缩块，glimpse 共 {counts['glimpse']} 次。",
              "", "| 浏览记录 | 答对 | 题数 |", "|---|---:|---:|"]
    for key,label in [(True,"至少一次收到网页正文的提取结果"),(False,"没有收到正文提取结果")]:
        v = by_visit[key]
        lines.append(f"| {label} | {v['correct']} | {v['n']} |")
    lines += ["", "## 用量", "", "| 角色 | 输入 token | 输出 token | 合计 token |", "|---|---:|---:|---:|"]
    for role, usage in [*sorted(bill.items()),("合计",total)]:
        lines.append(f"| {role} | {usage['prompt_tokens']:,} | {usage['completion_tokens']:,} | {usage['total_tokens']:,} |")
    lines += ["", f"按可核实回包估算，PACE 本轮约 ¥{cost(total):.2f}。680 条最终轨迹共 {counts['tokens']:,} token。"
              "用量表另计续跑时产生的失败尝试。切换到 PACE 单组前，中断且未落盘的调用缺少用量，供应商账单可能更高。",
              "", "动作、网页证据提取、摘要和裁判均使用 Labhuan Sonnet 4.6，PACE 使用本地 BGE-M3 INT8、128K 预算和 24 步上限。"
              "搜索从官方入口出发，对已发现的站内链接排序，网页按首次成功读取时的内容缓存。论文使用 Google 和 You.com，并以 GPT-4o 作裁判。"
              "这是一轮本机浏览环境评测。ReAct 只保留中止前的局部结果，无法据此计算同题全量增益。",
              "", "[逐题答案与判分](../results/webwalkerqa-full/pace-round1.jsonl) · [配置](../results/webwalkerqa-full/config.json) · [论文表 1 与附录 E](https://aclanthology.org/2026.acl-long.1252.pdf)"]
    (ROOT / "experiments/webwalkerqa-full-pace.md").write_text("\n".join(lines)+"\n")


if __name__ == "__main__":
    main()

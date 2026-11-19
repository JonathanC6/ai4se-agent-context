"""汇总四组实测，并展示每道题的匿名复评与末步回放。"""
from collections import Counter
from math import comb
from pathlib import Path
from urllib.parse import urlsplit

from benchmarks.webwalkerqa import CACHE, load_dataset
from cohorts import AUDIT, LABELS, PROJECT, cohorts, read, token_count
from pace.policy import Level


def yes(result):
    return int(result["grade"]["correct"])


def replay_outcome(r):
    return ("对" if yes(r) else "错") if r.get("grade") else "继续调用工具"


def actual_upgrades(step):
    adj = step.get("adjustment", {})
    upgrades = adj.get("upgrades", {})
    for c in step["chunks"]:
        i = str(c["id"])
        if i not in upgrades:
            continue
        base = upgrades[i][0]
        if c["summaries"] != "ready" and base in ("BRIEF", "DETAILED"):
            base = "FULL"
        if Level[c["shown"]] > Level[base]:
            yield (c["id"], base, c["shown"], c["id"] in adj["anchors"])


def exact_p(gains, losses):
    n = gains + losses
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(gains, losses) + 1)) / (2**n))


def address(url):
    parts = urlsplit(url)
    return parts.hostname, parts.path.rstrip("/"), parts.query


def main():
    episodes = {}
    directories = set()
    reused = 0
    sites = {}
    rows = load_dataset(CACHE)
    coverage = {}
    for n, plan, files in cohorts():
        group = [read(f) for f in files]
        episodes[n] = group
        directories.update(p.parent for p in files)
        if len(episodes) <= 20:
            reused += token_count(group[0]) + token_count(group[3])
        row = rows[n-1]
        if not all(r["row"] == n and r["question"] == row["question"] and "grade" in r for r in group):
            raise ValueError(f"incomplete or mismatched row {n}")
        name = plan["snapshots"][row["root_url"]]
        if name not in sites:
            sites[name] = {address(p["url"]) for p in read(CACHE / name)["pages"]}
        coverage[n] = all(address(u) in sites[name] for u in row["info"]["source_website"])
    out = ["# WebWalkerQA 四组消融 · 40 题", "",
           "A 为 PACE，B 加 DAG，C 再加 Anchor，D 再加 Superseded。每题每组各一条完整轨迹。第一批 A、D 直接读取原轨迹和原判分，两批分别核对题号、快照哈希、模型与预算。", "",
           "| 组 | 单源 | 多源 | 总分 | 第一批 / 第二批 | 步数 | 动作输入 | 动作输出 | 摘要 | 向量 | 评分 | 总 token |",
           "|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    for j, g in enumerate(LABELS):
        cases = [rs[j] for rs in episodes.values()]
        parts = [sum(yes(r) for r in cases if r["kind"] == t) for t in ("single_source", "multi_source")]
        u = Counter()
        for r in cases:
            for role, values in r["usage"].items():
                u[role] += values["total_tokens"]
            u["in"] += r["usage"]["actor"]["prompt_tokens"]
            u["out"] += r["usage"]["actor"]["completion_tokens"]
        out.append(f"| {g} | {parts[0]}/20 | {parts[1]}/20 | {sum(parts)}/40 | "
                   f"{sum(map(yes,cases[:20]))}/20 · {sum(map(yes,cases[20:]))}/20 | "
                   f"{sum(len(r['steps']) for r in cases)} | {u['in']:,} | {u['out']:,} | {u['summary']:,} | "
                   f"{u['embedding']:,} | {u['judge']:,} | {sum(map(token_count,cases)):,} |")
    out += ["", "| 组 | 标注页齐全子集 | 缺页子集 | 达到步数上限 | 使用过替代标记的轨迹 |",
            "|---|---:|---:|---:|---:|"]
    for j, g in enumerate(LABELS):
        present = [rs[j] for n, rs in episodes.items() if coverage[n]]
        missing = [rs[j] for n, rs in episodes.items() if not coverage[n]]
        limits = sum(rs[j]["status"] == "step_limit" for rs in episodes.values())
        replaced = sum(any(s.get("metadata", {}).get("replaced") for s in rs[j]["steps"]) for rs in episodes.values())
        out.append(f"| {g} | {sum(map(yes,present))}/{len(present)} | {sum(map(yes,missing))}/{len(missing)} | {limits} | {replaced} |")
    out += ["", "## 配对变化", "", "| 对照 | 错转对 | 对转错 | 总 token 差 | 双侧精确 McNemar p |",
            "|---|---:|---:|---:|---:|"]
    for a,b in ((0,1),(1,2),(2,3),(0,3)):
        gains = sum(yes(r[a]) < yes(r[b]) for r in episodes.values())
        losses = sum(yes(r[a]) > yes(r[b]) for r in episodes.values())
        delta = sum(token_count(r[b])-token_count(r[a]) for r in episodes.values())
        out.append(f"| {LABELS[a]} → {LABELS[b]} | {gains} | {losses} | {delta:+,} | {exact_p(gains,losses):.3f} |")
    out.extend(["", "## 逐题核对", "", "判分与 token 均按 A/B/C/D 顺序。1 为正确，0 为错误。末步提档只统计实际展示档位高于基础档位的块（不含锚点）。复评列列出同一份原始答案在再次独立评分时翻转的组。", "",
                "| 行号 | 题型 | 标注页齐全 | 首判 | 每题总 token | 末步非锚点依赖提档数 B/C/D | 同答案复评翻转 |",
                "|---:|---|---|---|---|---|---|"])
    evidence = []
    diagnostic_tokens = 0
    for n, rs in episodes.items():
        flags = [yes(r) for r in rs]
        mixed = len(set(flags)) > 1
        folder = AUDIT / str(n)
        flips = []
        if mixed:
            for g,r in zip(LABELS,rs):
                if yes(read(folder / f"regrade-{g}.json")) != yes(r):
                    flips.append(g)
        for p in folder.glob("*.json"):
            diagnostic_tokens += token_count(read(p))
        counts = [sum(not anchor for _,_,_,anchor in actual_upgrades(r["steps"][-1])) for r in rs[1:]]
        kind = "单源" if rs[0]["kind"] == "single_source" else "多源"
        out.append(f"| {n} | {kind} | {'是' if coverage[n] else '缺页'} | {''.join(map(str,flags))} | "
                   f"{' / '.join(f'{token_count(r):,}' for r in rs)} | {'/'.join(map(str,counts))} | "
                   f"{'、'.join(flips) or ('一致' if mixed else '无组间分歧，未复评')} |")
        if not mixed:
            continue
        evidence += [f"### 第 {n} 行", "", rs[0]["question"], "", "参考答案：" + rs[0]["reference"], ""]
        for g,r in zip(LABELS,rs):
            verdict = read(folder / f"regrade-{g}.json")["grade"]
            evidence += [f"**{g}**　首判 {yes(r)}，复评 {int(verdict['correct'])}。", "", r['answer'] or "步数上限内未提交。", "",
                         "首判依据：" + r['grade']['reason'], "", "复评依据：" + verdict["reason"], ""]
        replays = sorted(folder.glob("replay-*.json"))
        for p in replays:
            record = read(p)
            evidence += [f"- {p.stem}：{replay_outcome(record)}。涉及块 {record['ids']}。"]
        evidence.append("")
    out += ["", f"标注页按主机名、路径和查询串核对，共 {sum(coverage.values())}/40 题全部收录。缺页题保留在分母。"
            f"匿名复评与回放合计 {diagnostic_tokens:,} token，单独计量。", "",
            "## 如何读末步回放", "",
            "初次 A 错的分歧题中，按 B、C、D 顺序选首个初判正确且末步实际提升过非锚点依赖块的组。"
            "重建同一条轨迹的末步输入，并校验字节计数。每臂独立调用两次；一臂保持原样，另一臂仅将依赖块还原到 PACE 的基础档位。"
            "两臂使用相同的动作协议和评分器，继续浏览单列。这个诊断只测最后一步，无法隔离早期探索路径的影响。", "",
            "[分歧题原文与诊断](ablation40-evidence.md) · [逐题归因笔记](ablation40-notes.md)"]
    total = sum(token_count(r) for rs in episodes.values() for r in rs)
    interrupted = [read(p) for d in directories for p in d.glob("interrupted-*.json")]
    split = {n: [r["usage"].get("embedding", {}).get("split_inputs", 0) for r in rs] for n,rs in episodes.items()}
    split = {n: counts for n,counts in split.items() if any(counts)}
    out.extend(["", "## 新增调用与兼容处理", "",
                f"四组总用量 {total:,} token，其中 {reused:,} 来自上次已完成的 40 条记录。"
                f"本次 120 条正式轨迹共 {total-reused:,} token。另有 {len(interrupted)} 条中断记录，"
                f"已返回的用量合计 {sum(map(token_count,interrupted)):,} token；匿名评分与反事实诊断单列如上。"
                "排查接口时的独立公开文本探针另返回 8,196 个向量 token。没有 usage 的错误响应无法核对费用。", "",
                "部分 SIGCHI 长文本单条提交时返回上游参数错误 1210。原文本拆成两段后同一服务可以编码。"
                "四组对这类已拒绝的长输入采用相同规则，按两段 UTF-8 长度加权平均后沿用原有的向量归一化。"
                "模型、原文、网页快照均相同。以下为各组实际触发次数。", "",
                "| 行号 | A | B | C | D |", "|---:|---:|---:|---:|---:|"])
    out.extend("| " + " | ".join(map(str, [n, *counts])) + " |" for n, counts in split.items())
    for name, lines in [("ablation40.md",out),("ablation40-evidence.md",["# 分歧题原文与诊断","",*evidence])]:
        (PROJECT / "experiments" / name).write_text("\n".join(lines)+"\n")


if __name__ == "__main__":
    main()

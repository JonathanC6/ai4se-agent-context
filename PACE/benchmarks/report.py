"""从两组完整的本地轨迹生成可提交的逐题记录。"""
import json
from pathlib import Path
from statistics import mean
from urllib.parse import urlsplit

from .webwalkerqa import CACHE, ROOT, load_dataset


GROUPS = (ROOT, ROOT.parent / "DAG-PACE")


def metrics(result):
    usage = result["usage"]
    steps = result["steps"]
    return {
        "ok": result["grade"]["correct"],
        "kind": "单源" if result["kind"] == "single_source" else "多源",
        "steps": len(steps),
        "tokens": sum(role["total_tokens"] for role in usage.values()),
        "input": usage["actor"]["prompt_tokens"],
        "seconds": result["solver_seconds"] + result["judge_seconds"],
        "glimpses": result["glimpse_calls"],
        "upgrades": sum(len(s.get("adjustment", {}).get("upgrades", {})) for s in steps),
        "anchors": sum(bool(s.get("adjustment", {}).get("anchors")) for s in steps),
        "inactive": sum(bool(s.get("adjustment", {}).get("inactive")) for s in steps),
    }


def save(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def group_report(folder, cases):
    lines = [f"# {folder.name} · WebWalkerQA 20 题", "",
             "token 合计包括动作、摘要、向量和独立评分。动作输入单列，步数含 finish，耗时为求解与评分之和。并发运行时各题时间会重叠。", "",
             "| 行号 | 类型 | 判分 | 步数 | 动作输入 token | 全部 token | 秒 | glimpse |",
             "|---:|---|---|---:|---:|---:|---:|---:|"]
    for n, result in cases.items():
        m = metrics(result)
        lines.append(f"| {n} | {m['kind']} | {'对' if m['ok'] else '错'} | {m['steps']} | "
                     f"{m['input']:,} | {m['tokens']:,} | {m['seconds']:.1f} | {m['glimpses']} |")
    lines.extend(["", "## 题面、输出与判分依据", ""])
    for n, r in cases.items():
        lines.extend([f"### 第 {n} 行", "", r["question"], "", "**模型输出**", "",
                      r["answer"] or "达到运行上限，未提交答案。", "", "**参考答案**", "",
                      r["reference"], "", "**评分器说明**", "", r["grade"]["reason"], ""])
    save(folder / "experiments/paired20.md", lines)


def comparison(groups):
    base, dag = groups
    lines = ["# WebWalkerQA 配对评测", "",
             "每个组、每道题各运行一次。题单取 ACL 2023、ICSE、WWW 2024 范围内每种来源类型在主测试集中最先出现的十行。每组各四题并发、每题最多 16 步。独立评分会话使用同一模型和提示。", "",
             "| 组 | 题型 | 正确数 | 平均步数 | 动作输入 token | 全部 token | 每题平均秒数 |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for name, cases in zip(("PACE", "DAG-PACE"), groups):
        values = list(map(metrics, cases.values()))
        for kind in ("单源", "多源", "全部"):
            part = [x for x in values if kind == "全部" or x["kind"] == kind]
            lines.append(f"| {name} | {kind} | {sum(x['ok'] for x in part)}/{len(part)} | "
                         f"{mean(x['steps'] for x in part):.2f} | {sum(x['input'] for x in part):,} | "
                         f"{sum(x['tokens'] for x in part):,} | {mean(x['seconds'] for x in part):.1f} |")
    lines.extend(["", "## 同题差异", "",
                  "| 行号 | 类型 | PACE | DAG-PACE | 粒度提升次数 | 有锚点的步数 | 排除旧版本的步数 |",
                  "|---:|---|---|---|---:|---:|---:|"])
    for n in base:
        a, b = metrics(base[n]), metrics(dag[n])
        lines.append(f"| {n} | {a['kind']} | {'对' if a['ok'] else '错'} | "
                     f"{'对' if b['ok'] else '错'} | {b['upgrades']} | {b['anchors']} | {b['inactive']} |")
    # 覆盖率在运行结束后计算，标注页不进入模型上下文或选题过程。
    plan = json.loads(Path(__file__).with_name("paired20.json").read_text())
    dataset = load_dataset(CACHE)
    def address(url):
        parts = urlsplit(url)
        return parts.hostname, parts.path.rstrip("/"), parts.query
    missing = {}
    for root, filename in plan["snapshots"].items():
        pages = json.loads((CACHE / filename).read_text())["pages"]
        urls = {address(p["url"]) for p in pages}
        for n in base:
            if dataset[n - 1]["root_url"] == root:
                absent = [u for u in base[n]["reference_urls"] if address(u) not in urls]
                if absent:
                    missing[n] = absent
    lines.extend(["", "## 快照覆盖与配对变化", "",
                  f"按标注网址核对，{len(base)-len(missing)}/{len(base)} 题的全部标注页进入快照。"
                  "主结果保留全部 20 题。收录 URL 也不保证当前网页内容还原了出题时的版本。", ""])
    for n, absent in missing.items():
        links = "、".join(f"[{urlsplit(u).path}]({u})" for u in absent)
        lines.append(f"- 第 {n} 行缺少 {links}。")
    for label, condition in [("错转对", (False, True)), ("对转错", (True, False))]:
        changed = [str(n) for n in base if (metrics(base[n])["ok"], metrics(dag[n])["ok"]) == condition]
        lines.extend(["", f"{label}共 {len(changed)} 题。" + ("对应行号为 " + "、".join(changed) + "。" if changed else "")])
    lines.extend(["", "提升次数按每次决策、每个发生提档的旧块计数，含锚点。一次决策可提升多个块。只有题型、模型和工具等条件被固定；模型自报依赖也会改变提示和随后的行动，不能把单题翻转直接归因给某一条依赖边。",
                  "", "[基线答案与判分理由](../../PACE/experiments/paired20.md) · [改进组答案与判分理由](paired20.md)"])
    save(GROUPS[1] / "experiments/comparison.md", lines)


def main():
    groups = []
    configs = []
    for folder in GROUPS:
        data = folder / "results/paired20"
        config = json.loads((data / "config.json").read_text())
        configs.append({k: v for k, v in config.items() if k != "variant"})
        cases = {n: json.loads((data / f"row-{n}.json").read_text()) for n in config["rows"]}
        if len(cases) != 20 or sum(r["kind"] == "single_source" for r in cases.values()) != 10:
            raise ValueError("expected ten single-source and ten multi-source cases")
        for n, r in cases.items():
            if r["row"] != n or "grade" not in r:
                raise ValueError(f"incomplete row {n}")
        groups.append(cases)
    if configs[0] != configs[1]:
        raise ValueError("paired configurations differ")
    for folder, cases in zip(GROUPS, groups):
        group_report(folder, cases)
    comparison(groups)


if __name__ == "__main__":
    main()

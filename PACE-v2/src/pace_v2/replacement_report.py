"""从选定的轨迹生成固定 20 题的总体报告，失败开销单列。"""
from collections import Counter
import json
from pathlib import Path

from .study_report import DOC, LABELS


def input_tokens(record, role=None):
    roles = record["roles"]
    values = roles.values() if role is None else [roles[role]] if role in roles else []
    for v in values:
        if "visible_lo" not in v or v["visible_lo"]!=v["visible_hi"] or v.get("metered_calls",v["calls"])!=v["calls"]:
            raise ValueError("incomplete input measurement")
    return sum(v["visible_lo"] for v in values)


def answer_mark(value):
    return "✓" if value is True else "×" if value is False else "—"


def nums(seq):
    return "、".join(map(str,seq)) or "无"


def changes(rows,base,dag,scope):
    paired=[n for n in scope if all(type(rows[a][str(n)]["correct"]) is bool for a in (base,dag))]
    return paired,[n for n in paired if rows[dag][str(n)]["correct"] and not rows[base][str(n)]["correct"]], [
        n for n in paired if rows[base][str(n)]["correct"] and not rows[dag][str(n)]["correct"]]


def trace(out,comparison,arm,n):
    run=comparison["selected"].get(f"{arm}/{n}")
    if run:
        base=out/run
    else:
        base=out.parent/"dag-matched20"
    path=(base/"rep-1"/arm/f"row-{n}.json" if arm in ("pace","dag-pace") else base/arm/f"row-{n}"/"result.json")
    return json.loads(path.read_text()) if path.is_file() else {}


def difference_text(out,c,arm,n):
    # 同一条保留轨迹沿用已逐步核验过的证据；其他题直接列出实际动作和评分理由。
    known={("dag-pace",1):"全程使用全文。第 4 步多读项目 PDF，得到起止日期，算出 18 个月。",
           ("dag-pace",15):"第 6 步的草稿已有安全用水和 5,000 万美元；程序要求 Glimpse，下一步需 6,352 token，最终没有交卷。",
           ("dag-pace",21):"全程使用全文。把初步议程的 2 月 14 日答成最终议程的 2 月 21 日。",
           ("dag-pace",40):"两边都进了教师页。无 DAG 组重读科研项目段得到了 2020 年 1 月，DAG 组多次升档仍未取得起始时间。",
           ("pace-v2-dag",15):"第 5 步读到 5,000 万美元并写入事实清单，第 6 步才首次分档。关闭图升档的离线重放仍同时看得到 Water.org 和金额。",
           ("pace-v2-dag",157):"全程使用全文。DAG 组命中历史搜索并读到国机集团报道；另一组的新查询返回 HTTP 402。"}
    if (arm,n) in known:
        return known[arm,n]
    t=trace(out,c,arm,n)
    if not t:
        return "缺少逐步轨迹。"
    upgraded=[]
    for step in t["steps"]:
        adjustments=(step.get("adjustment") or {}).get("upgrades",{})
        ranks=("PLACEHOLDER","BRIEF","DETAILED","FULL")
        ids=[]
        for chunk in step["chunks"]:
            change=adjustments.get(str(chunk["id"]))
            if change:
                before=change[0]
                if before in ("BRIEF","DETAILED") and chunk["summaries"]!="ready":
                    before="FULL"
                if ranks.index(chunk["shown"])>ranks.index(before):
                    ids.append(chunk["id"])
        if ids:
            upgraded.append(f"第 {step['step']} 步 C"+"/C".join(map(str,ids)))
    route=" → ".join(h["kind"] for h in t["history"]) or "直接作答"
    grade=" ".join(t["grade"].get("reason","").split()).replace("|","／")
    if all((s.get("window") or {}).get("phase")=="full_history" for s in t["steps"]):
        note="决策全程为全文，旧块展开不能解释分差。"
    elif upgraded:
        note="实测升档包括"+"、".join(upgraded[:3])+"。这些步骤可定位证据，单条轨迹不能确认因果。"
    else:
        note="未记录到高于语义初选的旧块。"
    return f"{note} 工具顺序为 {route}。裁判记录「{grade}」"


def render(out,plan,c,data):
    rows=c["rows"]
    arms=plan["arms"]
    scope=plan["rows"]
    count=sum(type(v["correct"]) is bool for arm in arms for v in rows[arm].values())
    lines=["# 在 6,000 token 窗口下比较 ReAct、PACE 与 DAG","",
           f"五种方法共用固定的 20 道 WebWalkerQA 题，单源、多源各 10 道。已取得 {count}/100 个评分。每种方法只采用每题首次得到的有效评分。预算内未能交卷的轨迹按错题计；执行异常以缺测标出。","",
           "## 总体结果","","| 方法 | 答对 / 已评分 | 准确率 | 单源 / 多源答对 | 交卷 | 已评分轨迹的本地输入 token |","|---|---:|---:|---:|---:|---:|"]
    for a in arms:
        g=rows[a]
        done={int(n):v for n,v in g.items() if type(v["correct"]) is bool}
        wins=sum(v["correct"] for v in done.values())
        kinds=Counter(data[n-1]["info"]["type"] for n,v in done.items() if v["correct"])
        acc=f"{100*wins/len(done):.1f}%" if done else "—"
        lines.append(f"| {LABELS[a]} | {wins}/{len(done)} | {acc} | {kinds['single_source']} / {kinds['multi_source']} | {sum(v['submitted'] for v in done.values())} | {sum(input_tokens(v) for v in done.values()):,} |")
    lines+=["","## 同题配对与 token 开销",""]
    for base,dag in (("pace","dag-pace"),("pace-v2","pace-v2-dag")):
        paired,gain,loss=changes(rows,base,dag,scope)
        before,after=[sum(input_tokens(rows[a][str(n)]) for n in paired) for a in (base,dag)]
        scores=[sum(rows[a][str(n)]["correct"] for n in paired) for a in (base,dag)]
        delta=after-before
        lines+=[f"**{LABELS[base]}** 的 {len(paired)} 个有效配对中，从 {scores[0]} 题答对变为 {scores[1]} 题。错转对为 {nums(gain)}，对转错为 {nums(loss)}。同题可见输入从 {before:,} 变为 {after:,}，差额 {delta:+,}。",""]
    roles=("actor","visit","summary","plan","coverage","judge")
    lines+=["| 方法 | 动作 | 网页提取 | 历史摘要 | 事实规划 | 复核 | 裁判 | Glimpse 次数 |","|---|---:|---:|---:|---:|---:|---:|---:|"]
    for a in arms:
        done=[v for v in rows[a].values() if type(v["correct"]) is bool]
        cells=[f"{sum(input_tokens(v,role) for v in done):,}" for role in roles]
        lines.append("| "+" | ".join([LABELS[a],*cells,str(sum(v["tools"].get("glimpse",0) for v in done))])+" |")
    rejected=sum(sum(s.get("visible_lo",0) for s in t["roles"].values()) for key,ts in c["attempts"].items()
                 for t in ts if t["directory"]!=c["selected"].get(key))
    lines+=["",f"六题在线批次中，未形成采用评分的尝试另用了 {rejected:,} 个本地输入 token。上表只累计采用轨迹，复用部分按原记录与归档重建。","",
            "## 逐题结果","","✓ 为判对，× 为判错，— 为尚无评分。后两列记录旧块实际高于语义初选档位的块次。","",
            "| 题号 | 来源 | ReAct | 最新版 PACE | + DAG | PACE-v2 | v2 + DAG | 最新版升档 | v2 升档 |","|---:|---|:---:|:---:|:---:|:---:|:---:|---:|---:|"]
    for n in scope:
        rr=[rows[a][str(n)] for a in arms]
        kind="单源" if data[n-1]["info"]["type"]=="single_source" else "多源"
        lines.append("| "+" | ".join([str(n),kind,*[answer_mark(v["correct"]) for v in rr],
                     str(rr[2].get("visible_upgrades","—")),str(rr[4].get("visible_upgrades","—"))])+" |")
    lines+=["","## 哪些题的得分发生变化？",""]
    for base,dag in (("pace","dag-pace"),("pace-v2","pace-v2-dag")):
        _,gain,loss=changes(rows,base,dag,scope)
        for direction,nums_ in (("错转对",gain),("对转错",loss)):
            for n in nums_:
                lines.append(f"- **{LABELS[dag]}，第 {n} 题，{direction}。** {difference_text(out,c,dag,n)}")
    lines+=["","## 方法与实验条件","",
            "ReAct 保留完整历史。最新版 PACE 和独立 PACE-v2 在窗口占用达到 90% 时开始对旧块分档。v2 另建事实清单、保存草稿，并可在必要时缩短最近观察。DAG 根据模型标注的依赖、锚点和版本替代关系调整展示，同样受 6,000 token 上限约束。","",
            "模型为 Labhuan Claude Sonnet 4.6，温度 0，每题最多 24 步。裁判沿用 legacy-v1。每次模型调用按角色记录本地可见输入，以固定分词器计数并加消息开销。网关 usage 单列，不参与本轮压缩与截停。","",
            f"题号 {nums(plan['fresh'])} 在同一批次为五组分别实测；所有组对同一查询复用缓存，未命中时统一读取 DuckDuckGo 公开搜索的标题、摘要和链接。其他 14 题采用已有同题评分，当时的未缓存查询使用 You.com。两批共用网页读取器与评分规则。归档 ReAct 保留各题当时的动作协议。",""]
    target=out/DOC
    tmp=target.with_suffix(".md.tmp")
    tmp.write_text("\n".join(lines),encoding="utf-8")
    tmp.replace(target)

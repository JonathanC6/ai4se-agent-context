"""用评分完成的轨迹刷新五组对照文档；执行异常及缺测保留原状态。"""
from pathlib import Path

DOC = "WebWalkerQA五组DAG对照.md"
START = "<!-- study-results -->"
END = "<!-- end-study-results -->"
LABELS = {"react":"ReAct","pace":"最新版 PACE","dag-pace":"最新版 PACE + DAG",
          "pace-v2":"PACE-v2","pace-v2-dag":"PACE-v2 + DAG"}


def measured(rows):
    roles = [r for v in rows for r in v["roles"].values()]
    if not roles or any(r.get("metered_calls", r["calls"] if "visible_lo" in r else 0) < r["calls"] for r in roles):
        return "缺测"
    lo, hi = (sum(r[k] for r in roles) for k in ("visible_lo","visible_hi"))
    return f"{lo:,}" if hi == lo else f"{lo:,}–{hi:,}"


def update_document(template: Path, dest: Path, rows, pairs):
    text = template.read_text()
    before, section = text.split(START)
    _, after = section.split(END)
    lines = ["| 方法 | 已评分 / 20 | 答对 | 交卷 | 已评分轨迹的可见输入估值 |",
             "|---|---:|---:|---:|---:|"]
    for arm,label in LABELS.items():
        graded = [v for v in rows[arm].values() if type(v["correct"]) is bool]
        if not graded:
            lines.append(f"| {label} | 0/20 | — | — | — |")
            continue
        lines.append(f'| {label} | {len(graded)}/20 | {sum(v["correct"] for v in graded)} | '
                     f'{sum(v["submitted"] for v in graded)} | {measured(graded)} |')
    for arm, groups in pairs.items():
        complete = sum(len(nums) for key, nums in groups.items() if key != "unscored")
        if not complete:
            continue
        gains, losses = groups.get("gained", []), groups.get("lost", [])
        nums = lambda seq: "、".join(map(str,seq)) or "无"
        lines += ["",f'{LABELS[arm]} 有 {complete} 道题两侧都已评分。加 DAG 后，错转对的题号为 {nums(gains)}，'
                  f'对转错的题号为 {nums(losses)}。']
        if complete == 20:
            active = [n for n in gains if rows[arm][str(n)]["visible_upgrades"]]
            lines += ["", f'在错转对的题中，至少有一个块的实际展示档位高于语义初选的题号为 {nums(active)}。'
                      '还需逐题对照新增文字、后续动作和最终答案。']
    for arm,group in rows.items():
        failed = [n for n,v in group.items() if v["status"] == "execution_failed"]
        if failed:
            lines += ["",f'{LABELS[arm]} 的执行异常题号为 {"、".join(map(str,failed))}。']
        limited = [n for n,v in group.items() if v.get("search_rate_limited") and type(v["correct"]) is bool]
        if limited:
            lines += ["", f'{LABELS[arm]} 已评分的新轨迹中，搜索遇到临时限流的题号为 {"、".join(map(str,limited))}。']
    if all(all(type(v["correct"]) is bool for v in group.values()) for group in rows.values()):
        lines += ["", "各环节发给模型的可见输入估值如下。一次 Glimpse 可以直接读取内存，后续重新发送该观察产生的用量计入动作或摘要。",
                  "", "| 方法 | 动作 | 网页提取 | 历史摘要 | 事实规划 | 提交复核 | 裁判 | Glimpse 次数 |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for arm, group in rows.items():
            values = list(group.values())
            cells = []
            for role in ("actor","visit","summary","plan","coverage","judge"):
                matching = [dict(roles={role:v["roles"][role]}) for v in values if role in v["roles"]]
                cells.append(measured(matching) if matching else "0")
            glimpses = sum(v["tools"].get("glimpse", 0) for v in values)
            lines.append("| " + " | ".join([LABELS[arm], *cells, str(glimpses)]) + " |")
    dest.write_text(before + START + "\n\n" + "\n".join(lines) + "\n\n" + END + after)

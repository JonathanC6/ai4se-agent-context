"""复评同一答案并回放最后一步。诊断用量与四组主实验分开。"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from benchmarks.webwalkerqa import CACHE, CHAT, benchmark_chat, grade, load_dataset
from benchmarks.webwalker_snapshot import site_tools
from cohorts import AUDIT, LABELS, cohorts, read
from dag_pace.strategy import DependencyStrategy
from pace.agent import instructions
from pace.memory import Turn
from pace.policy import Level
from pace.providers import API, Utf8Counter
from pace.records import write_result


@lru_cache()
def browser(filename):
    snap = read(CACHE / filename)
    return snap["root"], site_tools(snap)


def replay_context(result, row, plan, label):
    root, tools = browser(plan["snapshots"][row["root_url"]])
    strategy = DependencyStrategy(anchors=label != "B", supersedes=label == "D")
    system = instructions(tools, 3) + "\n" + strategy.instructions
    query = (f"Website: {root}\nQuestion: {row['question']}\nUse search and visit to check the website "
             "before answering. If the pages lack the requested information, state what is missing.")
    original, reverted, changed = [query], [query], []
    step = result["steps"][-1]
    adj = step["adjustment"]
    for c in step["chunks"]:
        i = c["id"]
        h = result["history"][i - 1]
        full = Turn(h["thought"], h["action"], h["observation"], h["kind"]).text()
        versions = {"PLACEHOLDER": "", "FULL": full}
        if c["summaries"] == "ready":
            versions.update({key.upper(): value for key, value in h["summaries"].items()})
        shown = c["shown"]
        base = adj["upgrades"].get(str(i), [shown])[0]
        target = shown
        # 撤掉依赖提档，不触碰锚点、最近块或当时未完成的摘要。
        if (i in adj["ancestors"] and i not in adj["anchors"] and base in versions
                and Level[base] < Level[shown] and versions[base] != versions[shown]):
            target = base
            changed.append(i)
        for blocks, level in [(original, shown), (reverted, target)]:
            header = f"[C{i} {h['kind']} {level.lower()}]"
            blocks.append(header + ("\n" + versions[level] if versions[level] else ""))
    def messages(blocks):
        return [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(blocks)}]
    if Utf8Counter().messages(messages(original)) != step["input_tokens_estimate"]:
        raise ValueError("original prompt reconstruction mismatch")
    return changed, messages(original), messages(reverted)


def audit_row(item):
    n, row, plan, results = item
    grades = [r["grade"]["correct"] for r in results]
    if len(set(grades)) == 1:
        return
    folder = AUDIT / str(n)
    for label, result in zip(LABELS, results):
        dst = folder / f"regrade-{label}.json"
        if dst.exists():
            continue
        api = API.configured()
        verdict = grade(row, result["answer"], api, CHAT)
        write_result(dst, {"grade": verdict, "usage": api.usage})
    if grades[0]:
        return
    for label, result in zip(LABELS[1:], results[1:]):
        if not result["grade"]["correct"]:
            continue
        changed, original, reverted = replay_context(result, row, plan, label)
        if not changed:
            continue
        # 每题取首个合格的正向翻转组。交替顺序，每臂独立两次。
        for rep, arm in [(1, "original"), (1, "reverted"), (2, "reverted"), (2, "original")]:
            dst = folder / f"replay-{label}-{rep}-{arm}.json"
            if dst.exists():
                continue
            api = API.configured()
            action = benchmark_chat(api, CHAT, original if arm == "original" else reverted, "actor")
            answer = action.get("args", {}).get("answer") if action.get("tool") == "finish" else None
            verdict = grade(row, answer, api, CHAT) if answer else None
            write_result(dst, {"ids": changed, "action": action, "grade": verdict, "usage": api.usage})
        break
    print("audited", n, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    rows = load_dataset(CACHE)
    tasks = []
    for n, plan, files in cohorts():
        if all(p.is_file() for p in files):
            cases = [read(p) for p in files]
            if all("grade" in r for r in cases):
                tasks.append((n, rows[n-1], plan, cases))
    with ThreadPoolExecutor(args.jobs) as pool:
        list(pool.map(audit_row, tasks))


if __name__ == "__main__":
    main()

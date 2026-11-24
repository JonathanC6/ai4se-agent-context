"""同题核验 16K 下的判分、依赖提档和锚点占用。"""
from collections import Counter

from benchmarks.dynamic20_pace_report import summarize
from benchmarks.paper_pilot import question_prompt
from benchmarks.webwalker_budget20 import BASE, BUDGET
from benchmarks.webwalker_dynamic20 import DynamicBrowser
from benchmarks.webwalkerqa import CACHE, load_dataset
from dag_pace.strategy import DependencyStrategy
from pace.agent import instructions
from pace.memory import Turn
from pace.providers import Utf8Counter
from pace.records import write_result

from ablation_report import actual_upgrades
from cohorts import read
from run_budget20 import OUT


def minimum_input(raw, row):
    """本地超限时，复算保护锚点和释放锚点后的最低预算。"""
    if not raw.get("error", "").startswith("required context"):
        return None
    tools = DynamicBrowser(row["root_url"], None, raw["row"], OUT).tools()
    system = instructions(tools, 3) + "\n" + DependencyStrategy.instructions
    meta = [s["metadata"] for s in raw["steps"] if "metadata" in s]
    inactive = {i for m in meta for i in m["replaced"]}
    active = [h for h in raw["history"] if h["id"] not in inactive]
    recent = {h["id"] for h in active[-2:]}
    anchors = set(meta[-1]["anchors"]) if meta else set()

    def count(protected):
        blocks = [question_prompt(row["root_url"], row["question"])]
        for h in active:
            if h["id"] in protected:
                turn = Turn(h["thought"], h["action"], h["observation"], h["kind"])
                blocks.append(f"[C{h['id']} {h['kind']} full]\n{turn.text()}")
            else:
                blocks.append(f"[C{h['id']} {h['kind']} placeholder]")
        return Utf8Counter().messages([{"role": "system", "content": system},
                                      {"role": "user", "content": "\n\n".join(blocks)}])

    kept = count(recent | anchors)
    if f"need {kept} tokens" not in raw["error"]:
        raise ValueError(f"row {raw['row']}: failed to reproduce budget stop")
    # 删除策略说明时，UTF-8 预检值恰好减少这行文字的字节数。
    instruction_size = Utf8Counter().text("\n" + DependencyStrategy.instructions)
    return dict(protected=kept, released=count(recent), without_strategy_text=kept - instruction_size,
                old_anchors=sorted(anchors - recent))


def main():
    dataset = load_dataset(CACHE)
    baseline = BASE / "pace"
    config = read(baseline / "config.json")
    rows = config["rows"]
    if (config["budget"] != BUDGET or len(set(rows)) != 20 or len(rows) != 20
            or read(OUT / "config.json") != dict(config, arms=["dag-pace"])):
        raise ValueError("incompatible paired runs")
    report = {"groups": {}, "cases": {n: {} for n in rows}}
    for folder, arm in [(baseline, "pace"), (OUT, "dag-pace")]:
        cases, totals, _ = summarize(folder, arm, rows, dataset)
        totals["status"] = Counter(c["status"] for c in cases.values())
        totals["correct_by_type"] = Counter(c["kind"] for c in cases.values() if c["correct"])
        report["groups"][arm] = totals
        for n, stats in cases.items():
            report["cases"][n][arm] = stats
            if arm == "dag-pace":
                raw = read(folder / f"rep-1/{arm}/row-{n}.json")
                # API 超限时动作被丢弃；只统计实际通过预算检查的决策。
                stats["upgrades"] = {s["step"]: changes for s in raw["steps"]
                                     if s["input_tokens_actual"] <= BUDGET
                                     and (changes := list(actual_upgrades(s)))}
                stats["budget_replay"] = minimum_input(raw, dataset[n-1])
    write_result(OUT / "comparison.json", report)
    for arm, totals in report["groups"].items():
        print(arm, totals)


if __name__ == "__main__":
    main()

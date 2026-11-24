"""核查所有题含超限退出，按组和配对题汇总。"""
from collections import Counter
import json
from pace.agent import instructions
from pace.memory import Turn
from pace.providers import Utf8Counter
from pace.records import write_result
from .dynamic20_pace_report import summarize
from .paper_pilot import question_prompt
from .webwalker_budget20 import BUDGET, BASE, GROUPS, OUT
from .webwalker_dynamic20 import DynamicBrowser
from .webwalkerqa import load_dataset, CACHE


def steps_requiring_compression(raw, row, group, folder):
    # 固定同一条动作轨迹，只把每个历史块还原成全文，再用运行时的预算检查重算。
    tools = DynamicBrowser(row["root_url"], None, raw["row"], folder).tools()
    limit = {"react": 0, "pace": 3, "pace-guided": 1}[group]
    system = instructions(tools, limit, group == "pace-guided")
    blocks = [question_prompt(row["root_url"], row["question"])]
    counts = {}
    for i, step in enumerate(raw["steps"]):
        full = Utf8Counter().messages([{"role": "system", "content": system},
                                       {"role": "user", "content": "\n\n".join(blocks)}])
        if all(c["shown"] == "FULL" for c in step["chunks"]) and full != step["input_tokens_estimate"]:
            raise ValueError(f"full-history reconstruction mismatch at row {raw['row']} step {i+1}")
        if full > BUDGET and max(step["input_tokens_estimate"], step["input_tokens_actual"]) <= BUDGET:
            counts[i+1] = full
        if i < len(raw["history"]):
            h = raw["history"][i]
            turn = Turn(h["thought"], h["action"], h["observation"], h["kind"])
            blocks.append(f"[C{i+1} {turn.kind} full]\n{turn.text()}")
    return counts


def main():
    dataset = load_dataset(CACHE)
    rows = json.loads((OUT / "config.json").read_text())["rows"]
    if len(set(rows)) != 20 or len(rows) != 20:
        raise ValueError("expected the same 20 paired rows")
    groups = {}
    cases = {n: {} for n in rows}
    for group in GROUPS:
        folder = BASE / group
        arm = "react" if group == "react" else "pace"
        reference = OUT if arm == "react" else OUT.with_name(OUT.name+"-pace")
        expected = json.loads((reference / "config.json").read_text()) | {"budget": BUDGET}
        if group == "pace-guided":
            expected.update(glimpse_limit=1, guided_glimpse=True)
        if json.loads((folder / "config.json").read_text()) != expected:
            raise ValueError("configuration mismatch")
        records, totals, _ = summarize(folder, arm, rows, dataset)
        statuses, correct_by_type, budget_stops = Counter(), Counter(), Counter()
        capacity_steps = capacity_cases = 0
        valid = delivered = 0
        for n, stats in records.items():
            raw = json.loads((folder / f"rep-1/{arm}/row-{n}.json").read_text())
            good_steps = []
            for i, turn in enumerate(raw["history"]):
                if turn["kind"] == "glimpse" and not turn["observation"].startswith("Tool error:"):
                    good_steps.append(i+1)
            valid += len(good_steps)
            # 下步实际预算检查通过且回看块被展示，才算进入可用的下一轮。
            received = [step for step in good_steps if step < len(raw["steps"])
                        and raw["steps"][step].get("input_tokens_actual",0) <= BUDGET
                        and any(c["id"]==step and c["shown"]=="FULL" for c in raw["steps"][step]["chunks"])]
            delivered += len(received)
            kept = steps_requiring_compression(raw, dataset[n-1], group, folder)
            capacity_cases += bool(kept)
            capacity_steps += len(kept)
            if stats["status"] == "budget_exceeded":
                cause = "provider" if raw["error"].startswith("provider token count") else "preflight"
                budget_stops[cause] += 1
            cases[n][group] = dict(stats, glimpse_steps=good_steps, steps_requiring_compression=kept,
                                   delivered_glimpse_steps=received, error=raw.get("error"))
            statuses[stats["status"]] += 1
            correct_by_type[stats["kind"]] += stats["correct"]
        groups[group] = dict(totals, status=statuses, correct_by_type=correct_by_type,
                             budget_stops=budget_stops, capacity_steps=capacity_steps, capacity_cases=capacity_cases,
                             valid_glimpses=valid, delivered_glimpses=delivered)
    write_result(BASE / "comparison.json", dict(groups=groups, cases=cases))
    print(json.dumps(groups, indent=2))


if __name__ == "__main__":
    main()

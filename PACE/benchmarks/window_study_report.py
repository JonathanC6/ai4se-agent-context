"""核验同题对照，分别统计可见窗口、网关输入和已发生的 API 用量。"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from pace.records import write_result
from .actor_budget import PROTOCOL as ACTOR_PROTOCOL
from .research20 import read
from .window_study import study_rows
from .research_budget_audit import align_attempts, episode_events
from .webwalker_tools20 import measurements
from .webwalkerqa import CACHE, DATA_SHA, REVISION, load_dataset


COMPARISONS = (("react", "pace"), ("react", "dag-pace"),
               ("pace", "pace-window"), ("dag-pace", "dag-pace-window"),
               ("pace-window", "pace-delayed"), ("dag-pace-window", "dag-pace-delayed"))


def read_ledger(folder, arm, rows):
    events = defaultdict(lambda: defaultdict(list))
    billed = Counter()
    for index, line in enumerate((folder / "usage.jsonl").read_text().splitlines(), 1):
        event = json.loads(line)
        rep, n, recorded_arm = event["job"]
        if (rep, recorded_arm) != (1, arm) or n not in rows:
            raise ValueError(f"unexpected job at {folder}/usage.jsonl:{index}")
        role = event["role"]
        if any(type(event[k]) is not int or event[k] < 0
               for k in ("prompt_tokens", "completion_tokens", "total_tokens")):
            raise ValueError(f"invalid usage at {folder}/usage.jsonl:{index}")
        billed[role] += event["total_tokens"]
        events[n][role].append(dict(event, ledger_line=index))
    return events, billed


def verify_requests(record, events, cfg):
    # 逐题、逐角色复核实际计分的末次完整轨迹；流水还包括此前未完成的调用。
    for role, usage in record["usage"].items():
        n = usage["requests"]
        calls = events.get(role, [])[-n:] if n else []
        if len(calls) != n or any(sum(e[k] for e in calls) != usage[k]
                                  for k in ("prompt_tokens", "completion_tokens", "total_tokens")):
            raise ValueError(f"usage mismatch for {role}")
    if not record.get("actor_episode_id"):
        raise ValueError("missing actor episode id")
    owned, _ = episode_events(record, events.get("actor", []))
    attempts = align_attempts(record, owned)
    for event in owned:
        if not 0 < event["input_tokens_estimate"] <= cfg["budget"] or event["prompt_tokens"] <= 0:
            raise ValueError("actor sent a request outside the local window or without provider usage")
    for step in record["steps"]:
        if step["input_count_error"] != step["input_tokens_estimate"] - step["input_tokens_actual"]:
            raise ValueError("invalid input count error")
    oversize = [a for a in attempts if a["prompt_tokens"] > cfg["provider_input_budget"]]
    if oversize and (oversize != attempts[-1:] or record["status"] != "budget_exceeded"
                     or len(record["history"]) != oversize[0]["step"] - 1):
        raise ValueError("an over-budget response was used or retried")
    if record["status"] == "budget_exceeded":
        return "gateway" if oversize else "local_window"
    return None


def window_counts(record, accepted, cfg):
    windows = [s["window"] for s in record["steps"]]
    if record.get("budget_stop_window"):
        windows.append(record["budget_stop_window"])
    activation = None
    first_organized = None
    gate = cfg["compression_start_ratio"]
    if gate is not None:
        for i, w in enumerate(windows, 1):
            if activation is None and w["full_input_estimate"] >= gate * cfg["budget"]:
                activation = i
            if w["activation_step"] != activation:
                raise ValueError("gate differs from the first full-history threshold crossing")
            if w["first_organization_step"] is not None:
                first_organized = w["first_organization_step"]
    for step in record["steps"]:
        w = step["window"]
        if cfg["pressure_mode"] == "window":
            expected = min(1.0, w["current_input_estimate"] / cfg["budget"])
            if gate is not None and w["phase"] != "multilevel":
                expected = 0.0
            if abs(expected - step["pressure"]) > 1e-9:
                raise ValueError("recorded pressure does not match the window policy")
    full, organized = 0, 0
    compressed = capacity = 0
    for step in accepted:
        w = step["window"]
        shown = any(chunk["shown"] != "FULL" for chunk in step["chunks"])
        if shown and w["phase"] in ("full_history", "awaiting_old_chunk"):
            raise ValueError("compressed history before the gate allowed it")
        compressed += shown
        capacity += w["full_input_estimate"] > cfg["budget"]
        full += w["full_input_estimate"]
        organized += w["organized_input_estimate"]
    return dict(activation_step=activation, first_organization_step=first_organized,
                compressed_steps=compressed, full_history_over_budget_steps=capacity,
                full_estimated_tokens=full, organized_estimated_tokens=organized)


def case_metrics(record, row, n, arm, cfg, events):
    status = record["status"]
    correct = record["grade"]["correct"]
    if ((record["row"], record["arm"], record["repeat"], record["question"]) != (n, arm, 1, row["question"])
            or record["grade"]["version"] != cfg["grading_version"]
            or record["input_count_method"] != cfg["token_counter"]):
        raise ValueError("episode identity, grader or token counter differs")
    if status not in ("finished", "budget_exceeded", "step_limit") or type(correct) is not bool:
        raise ValueError("incomplete verdict")
    if (correct and status != "finished") or (status == "finished") != bool(record["answer"]):
        raise ValueError("verdict conflicts with final submission")
    steps = record["steps"]
    if len(steps) > cfg["max_steps"] or [s["step"] for s in steps] != list(range(1, len(steps) + 1)):
        raise ValueError("inconsistent decision sequence")
    stop = verify_requests(record, events, cfg)
    # 被网关拦截的末次决策已经计费，但模型动作未获准执行。
    accepted = steps[:-1] if stop == "gateway" else steps
    history = record["history"]
    if len(accepted) != len(history) + int(status == "finished"):
        raise ValueError("executed actions and history disagree")
    if status == "step_limit" and len(accepted) != cfg["max_steps"]:
        raise ValueError("premature step limit")
    stats = measurements(record, row, True)
    stats.update(window_counts(record, accepted, cfg))
    stats.update(row=n, kind=row["info"]["type"], status=status, budget_stop=stop,
                 steps=len(steps), executed_steps=len(accepted),
                 executed_peak=max((s["input_tokens_actual"] for s in accepted), default=0),
                 executed_visible_peak=max((s["input_tokens_estimate"] for s in accepted), default=0),
                 glimpse=sum(t["kind"] == "glimpse" for t in history),
                 reread=sum(t["kind"] == "reread" for t in history),
                 scored_tokens_by_role={k: u["total_tokens"] for k, u in record["usage"].items()})
    return stats


def report(dataset, output, groups):
    shared = None
    summary, cases = {}, {}
    episode_ids = set()
    for label, (arm, pressure, gate) in groups.items():
        folder = output / label
        cfg = read(folder / "config.json")
        replacements = [cfg["row_replacement"]] if "row_replacement" in cfg else cfg.get("row_replacements")
        rows = study_rows(dataset, replacements)
        common = cfg.copy()
        if ((common.pop("arms"), common.pop("pressure_mode"), common.pop("compression_start_ratio")) !=
            ([arm], pressure, gate) or (cfg["dataset"], cfg["sha256"], cfg["rows"]) != (REVISION, DATA_SHA, rows)
                or cfg["actor_budget_protocol"] != ACTOR_PROTOCOL or cfg["token_counter"] != "labhuan-visible-v1"):
            raise ValueError(f"unexpected condition or cohort: {label}")
        if shared is not None and shared != common:
            raise ValueError(f"shared configuration differs: {label}")
        shared = common
        events, billed = read_ledger(folder, arm, rows)
        group = []
        for n in rows:
            record = read(folder / f"rep-1/{arm}/row-{n}.json")
            if record["actor_episode_id"] in episode_ids:
                raise ValueError("same actor trajectory recorded twice")
            episode_ids.add(record["actor_episode_id"])
            case = case_metrics(record, dataset[n-1], n, arm, cfg, events[n])
            cases.setdefault(n, {})[label] = case
            group.append(case)
        scored = sum((Counter(c["scored_tokens_by_role"]) for c in group), Counter())
        if any(scored[k] > billed[k] for k in scored):
            raise ValueError(f"ledger below scored usage in {label}")
        counts = {k: sum(c[k] for c in group) for k in (
            "correct", "steps", "executed_steps", "compressed_steps", "full_history_over_budget_steps",
            "full_estimated_tokens", "organized_estimated_tokens", "glimpse", "reread", "any_hit", "all_hit")}
        published = dict(counts, n=len(group), correct_rows=[c["row"] for c in group if c["correct"]],
                         correct_by_type={kind: sum(c["correct"] for c in group if c["kind"] == kind)
                                          for kind in ("single_source", "multi_source")},
                         statuses=Counter(c["status"] for c in group),
                         budget_stops=Counter(c["budget_stop"] for c in group if c["budget_stop"]),
                         compressed_cases=sum(c["compressed_steps"] > 0 for c in group),
                         executed_peak=max(c["executed_peak"] for c in group),
                         executed_visible_peak=max(c["executed_visible_peak"] for c in group),
                         scored_tokens_by_role=scored, scored_tokens=sum(scored.values()),
                         ledger_tokens_by_role=billed, ledger_tokens=sum(billed.values()))
        if gate is not None:
            activated = [c["activation_step"] for c in group if c["activation_step"] is not None]
            published.update(activated=len(activated), never_activated=len(group) - len(activated),
                             first_activation_steps=activated,
                             organized_cases=sum(c["first_organization_step"] is not None for c in group))
        summary[label] = published
    paired = {}
    for before, after in COMPARISONS:
        if before not in groups or after not in groups:
            continue
        gains = [n for n in rows if not cases[n][before]["correct"] and cases[n][after]["correct"]]
        losses = [n for n in rows if cases[n][before]["correct"] and not cases[n][after]["correct"]]
        paired[f"{before}_to_{after}"] = dict(gains=gains, losses=losses, unchanged=len(rows)-len(gains)-len(losses))
    result = dict(config=shared, groups=summary, rows=cases, paired=paired)
    from .window_study import GROUPS
    if groups.keys() == GROUPS.keys():
        filename = "comparison.json"
    elif groups.keys() == {label for label, (_, _, gate) in GROUPS.items() if gate is None}:
        filename = "pressure-comparison.json"
    else:
        filename = "comparison-" + "-".join(label for label in GROUPS if label in groups) + ".json"
    write_result(output / filename, result)
    return result


def main():
    from .window_study import GROUPS, OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--groups", nargs="+", choices=GROUPS, default=list(GROUPS),
                        help="只核验并汇总选中的完整组，默认包含全部七组")
    args = parser.parse_args()
    if len(set(args.groups)) != len(args.groups):
        parser.error("duplicate groups")
    selected = {label: GROUPS[label] for label in args.groups}
    result = report(load_dataset(CACHE), args.out, selected)
    print(json.dumps(result["groups"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

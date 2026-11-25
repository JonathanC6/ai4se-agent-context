"""按逐请求账本离线审计动作预算，包括通过 JSON 重试前的响应。"""
import argparse
from collections import Counter, defaultdict
from functools import lru_cache
import json
from pathlib import Path
import re

from pace.records import write_result

DEFAULT = Path(__file__).resolve().parents[1] / "results/webwalker-research20"


def retry_token_delta(arm, config, directory):
    # 两条消息分别分词，格式补句只改变固定系统提示的长度。
    from pace.agent import instructions
    from pace.providers.encoding import LabhuanCounter, load_count_tokenizer
    from .paper_pilot import ASSETS
    from .research_browser import ResearchBrowser
    from .webwalkerqa import FORMAT_REMINDER
    tools = ResearchBrowser("https://example.invalid", None, 0, directory).tools()
    system = instructions(tools, 0 if arm == "react" else config.get("glimpse_limit", 3),
                          arm != "react" and config.get("guided_glimpse", False))
    if arm == "dag-pace":
        from dag_pace.strategy import DependencyStrategy
        system += "\n" + DependencyStrategy().instructions
    counter = LabhuanCounter(load_count_tokenizer(ASSETS / "tokenizer.json"))
    return counter.text(system + FORMAT_REMINDER) - counter.text(system)


def v2_outcome(record, attempts, budget, retry_delta):
    """沿已观测前缀核验重试预检、下一步残差及其对模型可见输入的影响。"""
    def outcome(proven, status, correct, reason, stop="original", steps=None, history=None):
        if proven and steps is None:
            steps, history = len(record["steps"]), len(record["history"])
        return dict(v2_equivalent=proven, v2_status=status, v2_correct=correct, v2_reason=reason,
                    v2_stop_reason=stop if proven else None, v2_steps=steps, v2_history_count=history)

    if record.get("actor_episode_id"):
        stop = "original"
        if record["status"] == "budget_exceeded":
            error = record.get("error", "")
            if error.startswith("provider"):
                stop = "provider"
            elif error.startswith("format retry"):
                stop = "retry_preflight"
        return outcome(True, record["status"], record["grade"]["correct"], "v2 recorded", stop)
    by_step = defaultdict(list)
    for attempt in attempts:
        by_step[attempt["step"]].append(attempt)
    previous_delta = 0
    for s in record["steps"]:
        step = s["step"]
        estimated = s["input_tokens_estimate"]
        if previous_delta:
            # pressure 由相同的上一步 API 实收决定；只有 fit 的预检可能因残差变化而不同。
            for chunk in s["chunks"]:
                expected = chunk["selected"]
                if expected in ("BRIEF", "DETAILED") and chunk["summaries"] != "ready":
                    expected = "FULL"
                if expected != chunk["shown"]:
                    return outcome(False, None, None, f"recheck fit demotion at step {step}")
            if estimated <= previous_delta:
                return outcome(False, None, None, f"recheck estimate floor at step {step}")
        for a in by_step[step]:
            retry = a["format_attempt"] == 2
            if retry and estimated == 1:
                return outcome(False, None, None, f"recheck floored retry estimate at step {step}")
            predicted = estimated - previous_delta + (retry_delta if retry else 0)
            if predicted > budget:
                return outcome(True, "budget_exceeded", False, f"v2 preflight at step {step} attempt {a['format_attempt']}",
                               "retry_preflight", step - 1, step - 1)
            if a["prompt_tokens"] > budget:
                return outcome(True, "budget_exceeded", False, f"provider at step {step} attempt {a['format_attempt']}",
                               "provider", step, step - 1)
        previous_delta = retry_delta if len(by_step[step]) == 2 else 0
    if previous_delta and record["status"] == "budget_exceeded":
        m = re.search(r"need (\d+) tokens", record.get("error", ""))
        if m is None or int(m[1]) - previous_delta <= budget:
            return outcome(False, None, None, "post-retry preflight may admit next step")
    return outcome(True, record["status"], record["grade"]["correct"], "all action inputs unchanged")


def match_legacy(steps, events):
    """每步最多两次 JSON 请求，以轨迹记录的最后一次实际输入数确定边界。"""
    @lru_cache(None)
    def align(step, pos):
        if step == len(steps):
            return [()] if pos == len(events) else []
        paths = []
        for count in (1, 2):
            end = pos + count
            if end > len(events) or events[end - 1]["prompt_tokens"] != steps[step]["input_tokens_actual"]:
                continue
            paths.extend((count, *tail) for tail in align(step + 1, end))
            if len(paths) > 1:
                break
        return paths[:2]

    paths = align(0, 0)
    if len(paths) != 1:
        raise ValueError("ambiguous ledger alignment" if paths else "no ledger alignment")
    return paths[0]


def episode_events(record, events):
    usage = record["usage"].get("actor", {})
    count = usage.get("requests", 0)
    episode_id = record.get("actor_episode_id")
    if episode_id:
        owned = [e for e in events if e.get("episode_id") == episode_id]
    else:
        # 同一组同一题串行执行。旧账本没有执行 ID，末尾完整一轮须与其用量逐项相等。
        owned = events[-count:] if count else []
    if len(owned) != count or (count and owned != events[-count:]):
        raise ValueError("completed episode is not an identifiable ledger suffix")
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if sum(e[key] for e in owned) != usage.get(key, 0):
            raise ValueError(f"ledger total mismatch: {key}")
    return owned, events[:len(events) - count]


def align_attempts(record, events):
    steps = record["steps"]
    if record.get("actor_episode_id"):
        groups = defaultdict(list)
        for event in events:
            groups[event["decision_step"]].append(event)
        counts = tuple(len(g) for g in groups.values())
        trailing_retry_stop = (record["status"] == "budget_exceeded" and
                               record.get("error", "").startswith("format retry needs "))
        if list(groups) != list(range(1, len(steps) + 1 + int(trailing_retry_stop))):
            raise ValueError("unexpected decision step ordering")
        for i, group in groups.items():
            if len(group) not in (1, 2) or [e["format_attempt"] for e in group] != list(range(1, len(group) + 1)):
                raise ValueError("unexpected format attempts")
            if i <= len(steps):
                if ((group[-1]["prompt_tokens"], group[-1]["input_tokens_estimate"]) !=
                    (steps[i - 1]["input_tokens_actual"], steps[i - 1]["input_tokens_estimate"])):
                    raise ValueError("logged response and trace differ")
            elif len(group) != 1:
                raise ValueError("unexpected request after preflight stop")
    else:
        counts = match_legacy(steps, events)
    attempts = []
    pos = 0
    for step, count in enumerate(counts, 1):
        for fmt in range(1, count + 1):
            event = events[pos]
            attempts.append(dict(ledger_line=event["ledger_line"], step=step, format_attempt=fmt,
                                 discarded_for_format=fmt < count or step > len(steps),
                                 prompt_tokens=event["prompt_tokens"], total_tokens=event["total_tokens"]))
            pos += 1
    return attempts


def audit_episode(record, events, budget, retry_delta=None):
    owned, discarded = episode_events(record, events)
    attempts = align_attempts(record, owned)
    if any(type(a["prompt_tokens"]) is not int or a["prompt_tokens"] < 1 for a in attempts):
        raise ValueError("missing valid provider input usage")
    first = next((a for a in attempts if a["prompt_tokens"] > budget), None)
    correct = record.get("grade", {}).get("correct")
    if type(correct) is not bool:
        raise ValueError("missing grade")
    return dict(scored=True, original_correct=correct, original_status=record["status"],
                **(v2_outcome(record, attempts, budget, retry_delta) if retry_delta is not None else {}),
                strict_correct=correct and first is None,
                strict_status="budget_exceeded" if first else record["status"],
                first_over_budget=first, attempts=attempts,
                discarded_run_actor_calls=len(discarded),
                discarded_run_actor_tokens=sum(e["total_tokens"] for e in discarded),
                discarded_run_over_budget_lines=[e["ledger_line"] for e in discarded if e["prompt_tokens"] > budget])


def audit(root):
    output = {}
    for arm in ("react", "pace", "dag-pace"):
        directory = root / arm
        config = json.loads((directory / "config.json").read_text())
        events = defaultdict(list)
        ledger = 0
        for i, line in enumerate((directory / "usage.jsonl").read_text().splitlines(), 1):
            event = json.loads(line)
            ledger += event["total_tokens"]
            if event["role"] == "actor":
                events[tuple(event["job"])].append(dict(event, ledger_line=i))
        cases = {}
        delta = retry_token_delta(arm, config, directory)
        if delta < 0:
            raise ValueError("format retry unexpectedly shortens the original system message")
        for n in config["rows"]:
            path = directory / f"rep-1/{arm}/row-{n}.json"
            try:
                record = json.loads(path.read_text())
                if (record["row"], record["arm"], record["repeat"]) != (n, arm, 1):
                    raise ValueError("episode identity mismatch")
                cases[n] = audit_episode(record, events[1, n, arm], config["budget"], delta)
            except (FileNotFoundError, KeyError, ValueError) as exc:
                charged = events[1, n, arm]
                cases[n] = dict(scored=False, reason=str(exc), charged_actor_calls=len(charged),
                                charged_actor_tokens=sum(e["total_tokens"] for e in charged))
        scored = [case for case in cases.values() if case["scored"]]
        first = [case["first_over_budget"] for case in scored if case["first_over_budget"]]
        summary = dict(denominator=len(cases), scorable=len(scored),
                       retry_delta=delta, v2_equivalent=sum(c["v2_equivalent"] for c in scored),
                       strict_correct=sum(c["strict_correct"] for c in scored),
                       original_correct=sum(c["original_correct"] for c in scored),
                       first_over_budget=len(first), first_on_retry=sum(a["format_attempt"] == 2 for a in first),
                       first_discarded_for_format=sum(a["discarded_for_format"] for a in first),
                       strict_status=Counter(c["strict_status"] for c in scored),
                       completed_episode_actor_calls=sum(len(c["attempts"]) for c in scored),
                       format_retry_calls=sum(a["format_attempt"] == 2 for c in scored for a in c["attempts"]),
                       discarded_run_actor_calls=sum(c["discarded_run_actor_calls"] for c in scored),
                       discarded_run_actor_tokens=sum(c["discarded_run_actor_tokens"] for c in scored),
                       ledger_tokens=ledger)
        output[arm] = dict(summary=summary, cases=cases)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT, help="含三组逐题轨迹的结果目录")
    args = parser.parse_args()
    result = audit(args.out)
    write_result(args.out / "strict-budget-audit.json", result)
    print(json.dumps({arm: data["summary"] for arm, data in result.items()}, indent=2))


if __name__ == "__main__":
    main()

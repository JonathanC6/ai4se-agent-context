"""用能证明等价的旧轨迹和必要的严格补跑，组成固定 20 题的三组比较。"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from pace.records import write_result
from .actor_budget import PROTOCOL
from .research20 import ARMS, OUT as STRICT, budget_audit, cohort, read
from .research_budget_audit import DEFAULT as ORIGINAL, audit_episode, retry_token_delta
from .webwalker_tools20 import measurements
from .webwalkerqa import CACHE, DATA_SHA, REVISION, load_dataset


def ledger(folder, arm):
    events = defaultdict(list)
    roles = defaultdict(Counter)
    path = folder / arm / "usage.jsonl"
    if path.exists():
        for i, line in enumerate(path.read_text().splitlines(), 1):
            event = json.loads(line)
            repeat, n, job_arm = event["job"]
            if repeat != 1 or job_arm != arm:
                raise ValueError(f"unexpected job in {path}:{i}")
            if event["role"] == "actor":
                events[n].append(dict(event, ledger_line=i))
            role = roles[event["role"]]
            role["requests"] += 1
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                role[key] += event[key]
    total = sum(roles.values(), Counter())
    return events, dict(roles=roles, total=total)


def configs(original, strict, rows):
    shared = None
    for folder, version in ((original, None), (strict, PROTOCOL)):
        for arm in ARMS:
            path = folder / arm / "config.json"
            if not path.exists():
                if any((folder / arm).glob("rep-1/*/row-*.json")):
                    raise ValueError(f"missing config for saved records: {path}")
                continue
            cfg = read(path)
            if (cfg.pop("arms") != [arm] or cfg["rows"] != rows
                    or cfg.pop("actor_budget_protocol", None) != version
                    or (cfg["dataset"], cfg["sha256"], cfg["budget"]) != (REVISION, DATA_SHA, 16000)):
                raise ValueError(f"unexpected protocol or workload: {path}")
            if shared is not None and cfg != shared:
                raise ValueError(f"model, tools or other settings differ: {path}")
            shared = cfg
    if shared is None:
        raise ValueError("expected at least one saved configuration")
    return shared


def reader_usage(path, turns):
    # reader 日志还包含失败重试及预算截断后的访问，只按有效轨迹对应的 URL 和快照日期计数。
    providers = {}
    if path.exists():
        for line in path.read_text().splitlines():
            kind, info = json.loads(line)
            if kind == "document":
                providers[info["url"], info["as_of"]] = info["backend"]
    counts = Counter()
    for turn in turns:
        if turn["kind"] != "visit" or not turn["observation"].startswith("["):
            continue
        for page in json.loads(turn["observation"]):
            if page["read"]:
                backend = providers.get((page["url"], page.get("as_of")))
                counts[backend or "unrecorded"] += 1
            else:
                counts["failed"] += 1
    return counts


def evaluate(folder, arm, n, row, cfg, events, strict, delta):
    path = folder / arm / f"rep-1/{arm}/row-{n}.json"
    if not path.exists():
        return None, "no saved episode"
    try:
        r = read(path)
        if "grade" not in r:
            raise ValueError("awaiting grade")
        if ((r["row"], r["arm"], r["repeat"], r["question"], r["grade"]["version"])
                != (n, arm, 1, row["question"], cfg["grading_version"])):
            raise ValueError("episode identity or judge mismatch")
        if r["status"] not in ("finished", "step_limit", "budget_exceeded"):
            raise ValueError("unrecognized terminal status")
        if type(r["grade"]["correct"]) is not bool or (r["status"] != "finished" and r["grade"]["correct"]):
            raise ValueError("invalid grade")
        if r["status"] == "finished" and (not isinstance(r["answer"], str) or not r["answer"].strip()
                or len(r["history"]) + 1 != len(r["steps"])):
            raise ValueError("missing submitted answer or decision")
        if any(s["step"] != i for i, s in enumerate(r["steps"], 1)):
            raise ValueError("decision steps out of order")
        budget_audit(r, cfg)
        audit = audit_episode(r, events, cfg["budget"], delta)
        first = audit["first_over_budget"]
        if strict != bool(r.get("actor_episode_id")):
            raise ValueError("episode id conflicts with the saved budget protocol")
        if strict and first and (first != audit["attempts"][-1] or r["status"] != "budget_exceeded"
                                 or len(r["history"]) != first["step"] - 1):
            raise ValueError("strict run acted after an over-budget response")
        if not audit["v2_equivalent"]:
            raise ValueError(audit["v2_reason"])
        status, correct = audit["v2_status"], audit["v2_correct"]
        steps, kept = audit["v2_steps"], audit["v2_history_count"]
        reason = audit["v2_reason"]
        if strict and r.get("error"):
            reason = r["error"]
        if not 0 <= kept <= len(r["history"]) or not kept <= steps <= cfg["max_steps"]:
            raise ValueError("invalid replay prefix")
        turns = r["history"][:kept]
        evidence = measurements(dict(history=turns, grade=dict(correct=correct)), row, True)
        recovery = Counter(t["kind"] for t in turns if t["kind"] in ("glimpse", "reread"))
        return dict(row=n, arm=arm, source="strict-live" if strict else "original-replay",
                    status=status, steps=steps, history_count=kept, reason=reason,
                    stop_reason=audit["v2_stop_reason"], ledger_first_over_budget=first, recovery=recovery,
                    reader_usage=reader_usage(folder / arm / f"reader-{n}.jsonl", turns), **evidence), None
    except (KeyError, TypeError, ValueError) as exc:
        return None, str(exc)


def compare(dataset, original, strict):
    if original.resolve() == strict.resolve():
        raise ValueError("the original and strict runs need separate ledgers")
    rows = cohort(dataset)
    cfg = configs(original, strict, rows)
    cases = []
    pending = {a: [] for a in ARMS}
    why = {a: {} for a in ARMS}
    billed = {"original": {}, "strict": {}}
    for arm in ARMS:
        old_events, billed["original"][arm] = ledger(original, arm)
        new_events, billed["strict"][arm] = ledger(strict, arm)
        delta = retry_token_delta(arm, cfg, original / arm)
        if delta < 0:
            raise ValueError("unexpected retry token delta")
        for n in rows:
            row = dataset[n - 1]
            case, old_problem = evaluate(original, arm, n, row, cfg, old_events[n], False, delta)
            if case is None:
                case, new_problem = evaluate(strict, arm, n, row, cfg, new_events[n], True, delta)
                if case is None:
                    pending[arm].append(n)
                    why[arm][n] = dict(original=old_problem, strict=new_problem)
                    continue
                case["replacement_reason"] = old_problem
            cases.append(case)
    groups = {}
    for arm in ARMS:
        chosen = [c for c in cases if c["arm"] == arm]
        groups[arm] = dict(scored=len(chosen), correct=sum(c["correct"] for c in chosen),
                           correct_by_type=Counter(dataset[c["row"]-1]["info"]["type"] for c in chosen if c["correct"]),
                           steps=sum(c["steps"] for c in chosen),
                           status=Counter(c["status"] for c in chosen), source=Counter(c["source"] for c in chosen),
                           any_hit=sum(c["any_hit"] for c in chosen), all_hit=sum(c["all_hit"] for c in chosen),
                           reader_usage=sum((Counter(c["reader_usage"]) for c in chosen), Counter()),
                           recovery=sum((Counter(c["recovery"]) for c in chosen), Counter()))
    for totals in billed.values():
        totals["total"] = sum((Counter(t["total"]) for t in totals.values()), Counter())
    return dict(config=cfg, pending=pending, reasons=why, groups=groups,
                rows=sorted(cases, key=lambda c: (c["row"], ARMS.index(c["arm"]))), billed=billed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "report"))
    parser.add_argument("--original", type=Path, default=ORIGINAL)
    parser.add_argument("--strict", type=Path, default=STRICT)
    parser.add_argument("--report-file", type=Path)
    args = parser.parse_args()
    result = compare(load_dataset(CACHE), args.original, args.strict)
    if args.command == "plan":
        print(json.dumps({k: result[k] for k in ("pending", "reasons")}, indent=2))
        return
    if any(result["pending"].values()):
        raise SystemExit("incomplete verified comparison: " + json.dumps(result["pending"]))
    path = args.report_file or args.strict / "verified-comparison.json"
    write_result(path, result)
    print(json.dumps(dict(groups=result["groups"], billed=result["billed"], report=str(path)), indent=2))


if __name__ == "__main__":
    main()

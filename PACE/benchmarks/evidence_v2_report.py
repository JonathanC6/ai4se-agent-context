"""从旧对照和新版逐题轨迹复算结果，核对题号、评分和单次调用流水。"""
import argparse
import json
from collections import Counter

from pace.policy import Settings
from pace.records import write_result
from .evidence_v2 import COHORT, CONTROL, OBSERVE_OUT, OUT
from .webwalkerqa import CACHE, load_dataset
from .window_study_report import case_metrics, read_ledger


def summarize(folder, dataset):
    cfg = json.loads((folder / "config.json").read_text())
    if cfg["rows"] != list(COHORT):
        raise ValueError("cohort differs")
    arm, = cfg["arms"]
    ledger, billed = read_ledger(folder, arm, COHORT)
    counts, roles, cases = Counter(), Counter(), {}
    failures_path = folder / "execution_failures.json"
    failures = json.loads(failures_path.read_text()) if failures_path.exists() else {}
    if not set(failures) <= {str(n) for n in COHORT}:
        raise ValueError("unknown failed row")
    for n in COHORT:
        path = folder / f"rep-1/{arm}/row-{n}.json"
        row = json.loads(path.read_text()) if path.exists() else {}
        if str(n) in failures:
            failure = failures[str(n)]
            if "grade" in row or len(failure["attempts"]) != 3 or not ledger[n]:
                raise ValueError(f"invalid terminal failure at row {n}")
            counts["ungraded"] += 1
            cases[n] = dict(correct=None, status="execution_failed", attempts=failure["attempts"])
            continue
        s = case_metrics(row, dataset[n-1], n, arm, cfg, ledger[n])
        roles.update(s["scored_tokens_by_role"])
        counts.update(correct=int(s["correct"]), finished=int(row["status"] == "finished"),
                      executed=s["executed_steps"], compressed=s["compressed_steps"],
                      capacity=s["full_history_over_budget_steps"], any_hit=int(s["any_hit"]),
                      all_hit=int(s["all_hit"]))
        counts[s["kind"]] += int(s["correct"])
        if s["budget_stop"]:
            counts[s["budget_stop"]] += 1
        recovery = []
        for step in row["steps"]:
            if cfg.get("method") == "evidence-v2":
                policy = Settings(cfg["horizon"], budget=cfg["budget"], pressure_mode="evidence-v2")
                w = step["window"]
                p = policy.pressure(step["step"], w["current_input_estimate"]) if w["phase"] == "multilevel" else 0.
                if abs(step["pressure"] - p) > 1e-9:
                    raise ValueError(f"unexpected pressure at row {n}, step {step['step']}")
            if "coverage" in step:
                counts["check_" + step["coverage"]["status"]] += 1
            if "recovery" in step:
                r = step["recovery"]
                counts[r["trigger"] + "_" + r["tool"]] += 1
                counts["tool_success"] += int(r["ok"])
                recovery.append(dict(step=step["step"], **r, review=step.get("evidence_review"),
                                     draft=step["action"].get("args", {}).get("answer")))
        cases[n] = dict(correct=s["correct"], status=row["status"], stop=s["budget_stop"],
                        steps=s["executed_steps"], compressed=s["compressed_steps"], recovery=recovery,
                        tokens=sum(s["scored_tokens_by_role"].values()), answer=row["answer"],
                        judge_reason=row["grade"].get("reason"))
    return dict(counts=counts, scored_by_role=roles, usage_ledger=billed, cases=cases)



def gateway_observations(folder):
    """区分网关报高值、最终轨迹实际收到的动作，以及中断重启的请求。"""
    cfg = json.loads((folder / "config.json").read_text())
    ledger, _ = read_ledger(folder, "pace", COHORT)
    result = {}
    for n in COHORT:
        events = ledger[n]["actor"]
        if any(not 0 < e["input_tokens_estimate"] <= cfg["budget"] or e["prompt_tokens"] <= 0 for e in events):
            raise ValueError(f"invalid actor input or usage at row {n}")
        high = [e for e in events if e["prompt_tokens"] > cfg["provider_input_budget"]]
        retries = {(e["episode_id"], e["decision_step"]) for e in events if e["format_attempt"] == 2}
        high_retried = sum(e["format_attempt"] == 1 and (e["episode_id"], e["decision_step"]) in retries
                           for e in high)
        path = folder / f"rep-1/pace/row-{n}.json"
        row = json.loads(path.read_text()) if path.exists() else {}
        final = [e for e in high if e["episode_id"] == row.get("actor_episode_id")]
        # 同一步可能有两条响应。只有最后一条能产生该步的动作。
        high_steps = [step["step"] for step in row.get("steps", [])
                      if step["input_tokens_actual"] > cfg["provider_input_budget"]]
        result[n] = dict(requests=len(events), over_reference=len(high), final_episode_over=len(final),
                         over_reference_steps=high_steps, over_reference_then_format_retry=high_retried,
                         visible_peak=max((e["input_tokens_estimate"] for e in events), default=0),
                         gateway_peak=max((e["prompt_tokens"] for e in events), default=0))
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observe-gateway", action="store_true", help="对照新版 PACE 的两次独立运行")
    args = parser.parse_args()
    data = load_dataset(CACHE)
    groups = {"react": CONTROL.parent, "legacy_pace": CONTROL.parent.parent / "pace", "evidence_v2": OUT}
    output = OUT
    if args.observe_gateway:
        output = OBSERVE_OUT
        old = json.loads((OUT / "config.json").read_text())
        new = json.loads((output / "config.json").read_text())
        if new != dict(old, enforce_provider_budget=False):
            raise ValueError("the paired runs differ beyond gateway enforcement")
        groups = {"enforced": OUT, "observed": output}
    result = {name: summarize(path, data) for name, path in groups.items()}
    if args.observe_gateway:
        result["observed"]["gateway_by_row"] = gateway_observations(output)
    write_result(output / "comparison.json", result)
    for name, group in result.items():
        print(name, dict(group["counts"]), sum(group["scored_by_role"].values()))


if __name__ == "__main__":
    main()

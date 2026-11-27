"""固定 20 题的五组对照。prepare 离线核对旧轨迹；run 只派发缺少的题。"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
from pathlib import Path

from benchmarks.evidence_v2 import COHORT, configuration
from benchmarks.paper_pilot import ASSETS, DenseEncoder, episode
from benchmarks.webwalkerqa import CACHE, DATA_SHA, load_dataset
from dag_pace.strategy import DependencyStrategy
from pace.providers.encoding import VisibleWindowCounter, load_count_tokenizer
from pace.records import write_result
from .benchmark import api_for, config as previous_config, one
from .browser import Browser, search_rate_limit
from .study_report import DOC, update_document
from .token_audit import audit_arm, ledger, read

ARMS = ("react", "pace", "dag-pace", "pace-v2", "pace-v2-dag")
RESULTS = Path(__file__).resolve().parents[2] / "results"
DEFAULT = RESULTS / "dag-matched20"
LEVEL = {"PLACEHOLDER": 0, "BRIEF": 1, "DETAILED": 2, "FULL": 3}


def archived_manifest(out):
    archive = RESULTS / "matched20-actions-v2-retry"
    current = previous_config()
    archived_config = read(archive / "config.json")
    if any(archived_config.get(k) != v for k, v in current.items()):
        raise ValueError("archived settings differ")
    data_path = CACHE / "main.jsonl"
    if hashlib.sha256(data_path.read_bytes()).hexdigest() != DATA_SHA:
        raise ValueError("dataset checksum differs")
    data = ledger(data_path)
    counter = VisibleWindowCounter(load_count_tokenizer(ASSETS / "tokenizer.json"))
    selected = read(archive / "comparison.json")["arms"]
    calls = {}
    manifest = {}
    for arm in ("react", "pace-v2"):
        rows = {}
        for n in COHORT:
            info = selected[arm]["rows"][str(n)]
            source = RESULTS / info["run"]
            # v2 的旧动作提示与本轮不同。只复用已经采用当前动作接口的题。
            if arm == "pace-v2" and source != archive:
                continue
            directory = source / arm / f"row-{n}"
            path = directory / "result.json"
            result = read(path)
            if (result["row"] != n or result["arm"] != arm or result["question"] != data[n-1]["question"]
                    or type(info["correct"]) is not bool or result["grade"]["correct"] != info["correct"]):
                raise ValueError(f"archived score mismatch at {arm} row {n}")
            if source not in calls:
                calls[source] = ledger(source / "usage.jsonl")
            events = [e for e in calls[source] if e["job"] == [1, n, arm]]
            audit = audit_arm(arm, [(result, events, directory / "sources")], counter, data, True)
            rows[str(n)] = dict(describe(result), source=source.name,
                                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                metering="replayed", roles=audit["roles"])
        manifest[arm] = rows
    write_result(out / "reuse.json", manifest)


def describe(result):
    upgrades = honored = used = automatic = anchors = replaced = 0
    for step in result["steps"]:
        graph = step.get("metadata", {})
        used += len(graph.get("used", []))
        automatic += len(set(graph.get("parents", [])) - set(graph.get("used", [])))
        anchors += bool(graph.get("anchors"))
        replaced += len(graph.get("replaced", []))
        proposals = (step.get("adjustment") or {}).get("upgrades", {})
        for chunk in step.get("chunks", []):
            change = proposals.get(str(chunk["id"]), proposals.get(chunk["id"]))
            if change:
                upgrades += 1
                before = change[0]
                if before in ("BRIEF","DETAILED") and chunk["summaries"] != "ready":
                    before = "FULL"  # 摘要尚未就绪时，无 DAG 的初选也会退回全文。
                honored += LEVEL[chunk["shown"]] > LEVEL[before]
    return dict(status=result["status"], correct=result["grade"]["correct"], submitted=bool(result["answer"]),
                steps=len(result["steps"]), tools=dict(Counter(h["kind"] for h in result["history"])),
                search_rate_limited=any(search_rate_limit(s.get("tool_error","")) for s in result["steps"])
                    or any(h["kind"]=="search" and search_rate_limit(h["observation"])
                           and h["observation"].startswith("Tool error:") for h in result["history"]),
                cited=used, automatic_edges=automatic, anchor_turns=anchors, replaced=replaced,
                proposed_upgrades=upgrades, visible_upgrades=honored)


def fresh_jobs(reused):
    # 同一题的组交错派发，避免某组总是先搜索或总在最后运行。
    jobs = []
    fresh = ARMS[1:]
    for i, n in enumerate(COHORT):
        for arm in fresh[i % len(fresh):] + fresh[:i % len(fresh)]:
            if str(n) not in reused.get(arm, {}):
                jobs.append((n, arm))
    return jobs


def run_one(n, arm, data, encoder, out, settings, *, retry_search=False,browser_class=Browser):
    strategy = DependencyStrategy if arm in ("dag-pace", "pace-v2-dag") else None
    if arm in ("react","pace-v2", "pace-v2-dag"):
        return one(n, arm, data[n-1], encoder, out, strategy, retry_search=retry_search,browser_class=browser_class)
    directory = out / arm / f"row-{n}"
    directory.mkdir(parents=True, exist_ok=True)
    failure = directory / "failure.json"
    if failure.exists():
        return n, arm, "previous_execution_failure"
    def browser_tools(root, api):
        browser = browser_class(root, api, n, directory, out / "shared-search")
        browser.retry_rate_limits = retry_search
        return browser.tools()
    try:
        episode((1, n, arm), settings, data, None, encoder, out,
                browser=browser_tools,
                api_factory=lambda: api_for(n, arm, out), strategy_factory=strategy)
        return n, arm, "scored"
    except Exception as exc:
        write_result(failure, dict(error=type(exc).__name__, detail=str(exc)[:260]))
        return n, arm, "execution_failed"


def summarize(out, reused):
    events = defaultdict(list)
    repair = out / "rate-retry"
    overhead = {}
    for source in (out, repair):
        if not (source / "usage.jsonl").exists():
            continue
        for event in ledger(source / "usage.jsonl"):
            _, n, arm = event["job"]
            events[source, arm, n].append(event)
    rows = {arm:dict(reused.get(arm, {})) for arm in ARMS}
    for n, arm in fresh_jobs(reused):
        source = repair if (repair / arm / f"row-{n}").is_dir() else out
        if source == repair:
            first = events[out, arm, n]
            overhead[f"{arm}/{n}"] = dict(requests=len(first),
                    visible_input=sum(e.get("visible_input_estimate",0) for e in first),
                    metered_calls=sum("visible_input_estimate" in e for e in first),
                    gateway_reported=sum(e["total_tokens"] for e in first))
        directory = source / arm / f"row-{n}"
        path = (source / "rep-1" / arm / f"row-{n}.json" if arm in ("pace", "dag-pace")
                else directory / "result.json")
        record = read(path) if path.exists() else {}
        if type(record.get("grade", {}).get("correct")) is bool:
            item = describe(record)
        elif (directory / "failure.json").exists():
            item = dict(status="execution_failed", correct=None)
        else:
            item = dict(status="pending", correct=None)
        roles = defaultdict(Counter)
        for e in events[source, arm, n]:
            r = roles[e["role"]]
            r["calls"] += 1
            if "visible_input_estimate" in e:
                r["visible_lo"] += e["visible_input_estimate"]
                r["visible_hi"] += e["visible_input_estimate"]
                r["metered_calls"] += 1
            if "output_text_subwords" in e:
                r["visible_output_subwords"] += e["output_text_subwords"]
                r["output_metered_calls"] += 1
            r["gateway_total"] += e["total_tokens"]
            r["gateway_incomplete"] += bool(e.get("gateway_usage_missing") or e.get("gateway_total_matches_parts") is False)
        rows[arm][str(n)] = dict(item, source="rate-retry" if source==repair else "current", metering="live", roles=roles)
    pairs = {}
    for base, dag in (("pace","dag-pace"), ("pace-v2","pace-v2-dag")):
        changes = defaultdict(list)
        for n in COHORT:
            a, b = (rows[k][str(n)]["correct"] for k in (base, dag))
            category = "unscored" if None in (a,b) else "same" if a == b else "gained" if b else "lost"
            changes[category].append(n)
        pairs[dag] = changes
    write_result(out / "comparison.json", dict(rows=rows, pairs=pairs, discarded_rate_attempts=overhead))
    template = RESULTS.parents[1] / "docs" / "WebWalkerQA五组DAG首轮.md"
    update_document(template, out / DOC, rows, pairs)
    return {arm:dict(scored=sum(type(v["correct"]) is bool for v in group.values()),
                     correct=sum(v["correct"] is True for v in group.values()),
                     failed=sum(v["status"]=="execution_failed" for v in group.values()))
            for arm, group in rows.items()}


def repair_limited(out, reused):
    # 等首轮释放锁，再按错误类型选题。已出分的题一律不重跑。
    with (out / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        settings = dict(configuration(observe_gateway=True), action_protocol="reviewed-json-v1")
        repair = out / "rate-retry"
        repair.mkdir(exist_ok=True)
        cache = repair / "shared-search"
        if not cache.exists():
            cache.symlink_to(out / "shared-search", target_is_directory=True)
        jobs = []
        for n, arm in fresh_jobs(reused):
            trial = out / arm / f"row-{n}"
            failure = trial / "failure.json"
            if failure.exists() and search_rate_limit(read(failure).get("detail","")):
                result = out / "rep-1" / arm / f"row-{n}.json" if arm in ("pace","dag-pace") else trial / "result.json"
                if not result.exists():
                    jobs.append((n, arm))
        write_result(repair / "jobs.json", jobs)
        print("UNSCORED SEARCH RATE LIMITS", jobs, flush=True)
        if jobs:
            data, encoder = load_dataset(CACHE), DenseEncoder()
            for n, arm in jobs:
                print("RETRY", *run_one(n, arm, data, encoder, repair, settings, retry_search=True), flush=True)
                failure = repair / arm / f"row-{n}" / "failure.json"
                if failure.exists() and search_rate_limit(read(failure).get("detail","")):
                    print("Search still rate limited after backoff; remaining first attempts retained", flush=True)
                    break
        print("END", summarize(out, reused), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "report", "repair-rate-limits"))
    parser.add_argument("--out", type=Path, default=DEFAULT)
    parser.add_argument("--jobs", type=int, default=3, choices=range(1, 9))
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.command == "prepare":
        archived_manifest(out)
        return
    reused = read(out / "reuse.json")
    if set(reused["react"]) != {str(n) for n in COHORT} or set(reused["pace-v2"]) != {"1","2","33","407"}:
        raise ValueError("unexpected reuse manifest")
    if args.command == "report":
        print(summarize(out, reused), flush=True)
        return
    if args.command == "repair-rate-limits":
        repair_limited(out, reused)
        return
    jobs = fresh_jobs(reused)
    settings = dict(configuration(observe_gateway=True), action_protocol="reviewed-json-v1")
    protocol = dict(settings, arms=list(ARMS), workload="five-arm-dag-matched20",
                    search_backend="historical-public-then-you-v1", reader="shared-archive-multiwindow-v1",
                    action_protocols={"pace":"reviewed-json-v1","dag-pace":"reviewed-json-v1",
                                      "pace-v2":"recoverable-actions-v2","pace-v2-dag":"recoverable-actions-v2",
                                      "react":"archived mixed, see reuse manifest"},
                    dag=dict(top_k=2, depths=2, anchors=True, supersedes=True),
                    reuse_sha256=hashlib.sha256((out / "reuse.json").read_bytes()).hexdigest(),
                    jobs=[list(j) for j in jobs])
    with (out / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        config_path = out / "config.json"
        if config_path.exists() and read(config_path) != protocol:
            raise ValueError("run configuration changed")
        write_result(config_path, protocol)
        data = load_dataset(CACHE)
        encoder = DenseEncoder()
        print("START", len(jobs), "fresh episodes", flush=True)
        with ThreadPoolExecutor(args.jobs) as pool:
            futures = [pool.submit(run_one, n, arm, data, encoder, out, settings) for n,arm in jobs]
            for future in as_completed(futures):
                print("RESULT", *future.result(), flush=True)
        print("END", summarize(out, reused), flush=True)


if __name__ == "__main__":
    main()

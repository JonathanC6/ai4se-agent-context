"""离线重建固定 20 题的可见输入，独立于网关 usage。只读取已有归档。"""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from types import SimpleNamespace

from benchmarks.google_you import items
from benchmarks.paper_pilot import ASSETS, CHAT, extract_page
from benchmarks.source_evidence import Source, SourceEvidence
from benchmarks.webwalkerqa import CACHE, DATA_SHA, FORMAT_REMINDER, grade
from pace.context import Selection
from pace.memory import Turn
from pace.policy import Level
from pace.providers import API
from pace.providers.encoding import VisibleWindowCounter, load_count_tokenizer
from .browser import Archive
from .evidence import Checklist, Fact

ROOT = Path(__file__).resolve().parents[3]
OLD = ROOT / "PACE/results/webwalker-window-study-matched20"
ORIGINAL = ROOT / "PACE-v2/results/matched20-facts-v1"
RERUN = ROOT / "PACE-v2/results/matched20-actions-v2-retry"


def read(path):
    return json.loads(path.read_text())


def ledger(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


class Capture:
    """使用生产提示构造函数，不连接模型。保存每次初始请求和格式重试的估值。"""
    def __init__(self, counter):
        self.counter = counter
        self.step = 0
        self.calls = defaultdict(list)

    def chat(self, model, messages, role, **kwargs):
        step = -1 if role == "judge" else self.step
        reminder = [dict(messages[0], content=messages[0]["content"] + FORMAT_REMINDER), *messages[1:]]
        self.calls[step, role].append((self.counter.messages(messages), self.counter.messages(reminder)))
        return dict(detailed="offline", brief="offline", correct=False)


def replay_browser(h, archive, directory):
    args = json.loads(h["action"])["args"]
    if h["kind"] == "reread":
        if not h["observation"].startswith("Tool error:"):
            observed = json.loads(h["observation"])
            rebuilt = json.loads(archive.reread(args))
            def spans(obj):
                return [p["window"] for p in obj.get("passages", [obj])]
            if observed["source_id"] != rebuilt["source_id"] or spans(observed) != spans(rebuilt):
                raise ValueError("reread did not select the archived passages")
        return
    if h["kind"] != "visit" or h["observation"].startswith("Tool error:"):
        return
    rows = json.loads(h["observation"])
    goals = items(args["goal"])
    if len(goals) == 1:
        goals *= len(rows)
    if len(goals) != len(rows):
        raise ValueError("visit goals do not match the saved responses")
    for row, goal in zip(rows, goals):
        if "text_sha256" not in row:
            continue
        digest = row["text_sha256"]
        data = (directory / (digest + ".txt")).read_bytes()
        if sha256(data).hexdigest() != digest:
            raise ValueError("page hash mismatch")
        text = data.decode("utf-8")
        start, end = row["window"]
        url = row["source"]
        archive.sources[row["source_id"]] = Source(url, text, digest, start)
        extract_page(archive.api, url, goal, text, start, end)


def review_context(step, history):
    selections = []
    for chunk in step["chunks"]:
        h = history[chunk["id"] - 1]
        level = Level[chunk["shown"]]
        text = {Level.FULL: "", Level.PLACEHOLDER: "", Level.BRIEF: h["summaries"]["brief"],
                Level.DETAILED: h["summaries"]["detailed"]}[level]
        saved = SimpleNamespace(id=h["id"], turn=SimpleNamespace(kind=h["kind"]))
        selections.append(Selection(saved, {level:text}, level, level, None, None, "ready"))
    return SimpleNamespace(selections=selections)


def replay(record, row, arm, directory, current, counter):
    api = Capture(counter)
    book = None
    archive = Archive(api) if current else SourceEvidence(api)
    facts = []
    if arm == "pace-v2":
        Checklist.plan(api, row["question"])
        stored = record["checklist"]
        book = Checklist(row["question"], list(stored["needs"].values()))
        facts = [Fact(**v) for v in stored["evidence"]]
    history = record["history"]
    drafts = {d["step"]: d["answer"] for d in record.get("drafts", [])}
    reviews = 0
    for step in record["steps"]:
        i = api.step = step["step"]
        review = step.get("review")
        if book and i in drafts and i < 24 and reviews < 2:
            tried = set(book.tried)
            book.review(api, drafts[i], review_context(step, history), archive)
            book.tried = tried
            if review:
                book.tried.add((review["slot"], review["target"]))
                reviews += 1
        if i > len(history):
            continue
        h = history[i-1]
        replay_browser(h, archive, directory)
        if book:
            if h["kind"] == "glimpse":
                restored = json.loads(h["action"])["args"]["ids"]
            else:
                restored = ()
            book.digest(api, h["kind"], h["observation"], i, archive, restored)
            added = [f for f in facts if f.chunk == i]
            book.facts.extend(added)
            if review:
                book.check_recovery(api, review, added)
        elif arm == "pace":
            turn = Turn(h["thought"], h["action"], h["observation"], h["kind"])
            API.summarize(api, CHAT, turn.text())
    grade(row, record["answer"], api, CHAT, record["grade"]["version"])
    return api.calls


def selected_events(events, record):
    """历史目录含多次整题启动。用逐题末次 usage 和 actor episode id 双重核验。"""
    selected = []
    for role, usage in record["usage"].items():
        count = usage["requests"]
        matches = [i for i,e in enumerate(events) if e["role"] == role]
        indices = matches[-count:] if count else []
        rows = [events[i] for i in indices]
        if len(rows) != count or any(sum(e[k] for e in rows) != usage[k]
                for k in ("prompt_tokens","completion_tokens","total_tokens")):
            raise ValueError(f"ledger mismatch at row {record['row']} / {role}")
        if role == "actor" and any(e["episode_id"] != record["actor_episode_id"] for e in rows):
            raise ValueError("actor episode mismatch")
        selected.extend(indices)
    return [events[i] for i in sorted(selected)]


def estimate_calls(prompts, count, role):
    # 同一角色同一步有多段网页时，旧日志未指出哪一段重试。保留可核验的上下界。
    retry = count - len(prompts)
    if not 0 <= retry <= len(prompts):
        raise ValueError(f"{role}: replay produced {len(prompts)} prompts for {count} responses")
    retry_sizes = sorted(size for _,size in prompts)
    base = sum(size for size,_ in prompts)
    lo = base + sum(retry_sizes[:retry])
    hi = base + (sum(retry_sizes[-retry:]) if retry else 0)
    return lo, hi


def bucket(step, role, current):
    # 旧 PACE 的摘要异步完成，只能按题对齐。网页提取始终在相应动作内同步执行。
    if role == "judge":
        return -1, role
    return (0 if role == "summary" and not current else step), role


def audit_arm(arm, records, counter, dataset, current):
    stats = defaultdict(Counter)
    tools = Counter()
    actors = []
    for record, events, pages in records:
        selected = selected_events(events, record)
        ac = [e for e in selected if e["role"] == "actor"]
        actors.extend(ac)
        tools.update(h["kind"] for h in record["history"])
        counts = Counter()
        step = 0
        for e in selected:
            role = e["role"]
            s = stats[role]
            s["calls"] += 1
            s["gateway_in"] += e["prompt_tokens"]
            s["gateway_out"] += e["completion_tokens"]
            s["gateway_total"] += e["total_tokens"]
            if e["total_tokens"] != e["prompt_tokens"] + e["completion_tokens"]:
                raise ValueError("inconsistent gateway usage")
            if role == "actor":
                step = e["decision_step"]
                estimate = e["input_tokens_estimate"]
                s["visible_lo"] += estimate
                s["visible_hi"] += estimate
                if e["format_attempt"] > 1:
                    s["additional_calls"] += 1
                    s["additional_visible"] += estimate
            else:
                counts[bucket(step, role, current)] += 1
        prompts = replay(record, dataset[record["row"]-1], arm, pages, current, counter)
        buckets = defaultdict(list)
        for (i,role), calls in prompts.items():
            buckets[bucket(i,role,current)].extend(calls)
        for key in counts.keys() | buckets.keys():
            role = key[1]
            try:
                lo,hi = estimate_calls(buckets[key], counts[key], role)
            except ValueError as exc:
                raise ValueError(f"{arm} row {record['row']} bucket {key}: {exc}") from exc
            stats[role]["visible_lo"] += lo
            stats[role]["visible_hi"] += hi
    n = len(actors)
    ids = [e["response_id"] for e in actors if e.get("response_id")]
    caches = [e.get("prompt_cache_details",{}) for e in actors]
    retries = []
    for first, second in zip(actors, actors[1:]):
        if (first["episode_id"] == second["episode_id"] and
                first["decision_step"] == second["decision_step"] and
                (first["format_attempt"],second["format_attempt"]) == (1,2) and
                "message_chars" in first and "message_chars" in second):
            retries.append(dict(row=first["job"][1], step=first["decision_step"],
                added_chars=second["message_chars"]-first["message_chars"],
                local=[e["input_tokens_estimate"] for e in (first,second)],
                gateway=[e["prompt_tokens"] for e in (first,second)]))
    def gap(pair):
        return abs(pair["gateway"][0]-pair["gateway"][1])
    return dict(roles=stats, tools=tools, actor=dict(calls=n,
        ids=len(ids), unique_ids=len(set(ids)), hashes=len({e["messages_sha256"] for e in actors if "messages_sha256" in e}),
        over_6000=sum(e["prompt_tokens"]>6000 for e in actors),
        over_80000=sum(e["prompt_tokens"]>80000 for e in actors),
        peak_local=max(e["input_tokens_estimate"] for e in actors),
        peak_gateway=max(e["prompt_tokens"] for e in actors),
        median_ratio=median(e["prompt_tokens"]/e["input_tokens_estimate"] for e in actors),
        retry_pairs_with_lengths=len(retries), retry_pairs_gap_over_10k=sum(gap(p)>10000 for p in retries),
        largest_retry_gap=max(retries,key=gap) if retries else None,
        cache_read=sum(c.get("cached_tokens",0) for c in caches),
        cache_write=sum(c.get("cached_creation_tokens",0) for c in caches)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    def path(p):
        return args.root / p.relative_to(ROOT)
    dataset_file = path(CACHE)/"main.jsonl"
    if sha256(dataset_file.read_bytes()).hexdigest() != DATA_SHA:
        raise ValueError("WebWalkerQA snapshot differs from the recorded benchmark")
    dataset = ledger(dataset_file)
    counter = VisibleWindowCounter(load_count_tokenizer(path(ASSETS)/"tokenizer.json"))
    combined = read(path(RERUN)/"comparison.json")["arms"]
    all_stats = {}
    for name, arm, current in (("react","react",True),("pace-v2","pace-v2",True),
                               ("historical-react","react",False),("historical-pace","pace",False)):
        runs = {}
        records = []
        for n in combined["react"]["rows"]:
            if current:
                run = path(ORIGINAL).parent / combined[arm]["rows"][n]["run"]
                directory = run / arm / f"row-{n}"
                result = directory / "result.json"
                pages = directory / "sources"
            else:
                run = path(OLD) / arm
                result = run / "rep-1" / arm / f"row-{n}.json"
                pages = run / "sources"
            if run not in runs:
                runs[run] = ledger(run/"usage.jsonl")
            events = [e for e in runs[run] if e["job"] == [1,int(n),arm]]
            records.append((read(result),events,pages))
        all_stats[name] = audit_arm(arm, records, counter, dataset, current)
    print(json.dumps(all_stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

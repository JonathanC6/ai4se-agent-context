"""运行完整 WebWalkerQA main。每轮每组的分母固定为 680。"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
import threading
from pathlib import Path
from time import monotonic, sleep

from pace.records import write_result
from pace.providers import API, ProviderError, json_object
from .full_webwalker_preflight import OUT
from .paper_pilot import CAP, ENCODER, DenseEncoder, episode
from .grading import grading_settings
from .webwalker_live import Browser, CURRENT_BROWSER, LEGACY_BROWSER, hostname, received_page_text
from .webwalkerqa import CACHE, CHAT, DATA_SHA, REVISION, load_dataset


class FullRunAPI(API):
    """逐请求落盘用量，保留中途失败的调用成本。"""
    journal_lock = threading.Lock()

    def parse_reply(self, content):
        try:
            return json_object(content)
        except json.JSONDecodeError as exc:
            # 仅修复字符串中紧跟普通文字的裸引号，不推断缺失字段或布尔判分。
            if exc.msg != "Expecting ',' delimiter":
                raise
            source = exc.doc
        escaped = []
        inside = False
        i = 0
        while i < len(source):
            char = source[i]
            if inside and char == chr(92) and i + 1 < len(source):
                escaped.extend(source[i:i+2])
                i += 2
                continue
            if char == '"':
                rest = source[i+1:].lstrip() if inside else ""
                if inside and rest.startswith(('"', '{', '[')):
                    raise ValueError("ambiguous JSON string boundary")
                if inside and rest and rest[0] not in ",:]}":
                    escaped.append(chr(92))
                else:
                    inside = not inside
            escaped.append(char)
            i += 1
        parsed = json_object("".join(escaped))
        print("restored JSON string quoting", self.job, flush=True)
        return parsed

    def post(self, path, body, purpose):
        for attempt in range(3):
            try:
                result = super().post(path, body, purpose)
                break
            except ProviderError as exc:
                if attempt == 2 or not any(tag in str(exc) for tag in
                        ("HTTP 429", "HTTP 502", "HTTP 503", "HTTP 504", "URLError",
                         "TimeoutError", "RemoteDisconnected", "ConnectionResetError")):
                    raise
                sleep(2 ** (attempt + 1))
        usage = result.get("usage") or {}
        choice = (result.get("choices") or [{}])[0]
        line = {"job": self.job, "role": purpose, "finish_reason": choice.get("finish_reason"),
                **{k: usage.get(k, 0) for k in ("prompt_tokens","completion_tokens","total_tokens")}}
        if purpose == "actor" and hasattr(self, "actor_log"):
            line.update(self.actor_log)
            details = usage.get("prompt_tokens_details")
            if isinstance(details, dict):
                # 缓存读写是 prompt_tokens 的分项，账单总计只加服务端 total_tokens。
                line["prompt_cache_details"] = {k: details[k] for k in ("cached_tokens", "cached_creation_tokens")
                                                if type(details.get(k)) is int}
            if isinstance(result.get("model"), str):
                line["response_model"] = result["model"]
        with self.journal_lock, (self.output / "usage.jsonl").open("a") as f:
            f.write(json.dumps(line) + "\n")
        return result


def report(dataset, config, output=None):
    output = OUT if output is None else output
    totals = []
    for rep in range(1, config["repeats"] + 1):
        for arm in config["arms"]:
            counts = Counter()
            tokens = Counter()
            types = Counter()
            for n, row in enumerate(dataset, 1):
                path = output / f"rep-{rep}/{arm}/row-{n}.json"
                if not path.exists():
                    continue
                record = json.loads(path.read_text())
                grade = record.get("grade", {}).get("correct")
                if type(grade) is not bool:
                    continue
                counts["graded"] += 1
                counts["correct"] += grade
                counts["steps"] += len(record["steps"])
                counts["tool_error_cases"] += any(t["observation"].startswith("Tool error:") for t in record["history"])
                counts["no_successful_visit"] += not any(received_page_text(t) for t in record["history"])
                counts[record["status"]] += 1
                types[row["info"]["type"]] += grade
                for role, usage in record["usage"].items():
                    tokens[role] += usage["total_tokens"]
            full = counts["graded"] == len(dataset)
            totals.append(dict(repeat=rep, arm=arm, counts=counts, correct_by_type=types, tokens=tokens,
                               missing=len(dataset)-counts["graded"], accuracy=counts["correct"]/len(dataset) if full else None))
    write_result(output / "summary.json", totals)
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "report"])
    parser.add_argument("--arms", nargs="+", choices=["pace", "react"], default=["pace"])
    parser.add_argument("--repeats", type=int, choices=[1, 3], default=1)
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    output = args.out
    dataset = load_dataset(CACHE)
    if len(dataset) != 680 or args.jobs < 1 or len(set(args.arms)) != len(args.arms):
        parser.error("invalid split, job count or duplicate arms")
    cfg = output / "config.json"
    if args.command == "report":
        print(report(dataset, json.loads(cfg.read_text()), output))
        return
    output.mkdir(parents=True, exist_ok=True)
    lock = (output / "run.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    preflight = output / "preflight.json"
    if not preflight.exists():
        preflight = OUT / "preflight.json"
    probes = json.loads(preflight.read_text())["probes"]
    sites = {root: sorted({hostname(root), hostname(p.get("url", root))}) for root,p in probes.items()}
    old = json.loads(cfg.read_text()) if cfg.exists() else None
    protocol = old["protocol"] if old else CURRENT_BROWSER
    if protocol not in (LEGACY_BROWSER, CURRENT_BROWSER):
        raise ValueError("unknown saved browser protocol")
    config = dict(protocol=protocol, dataset=REVISION, sha256=DATA_SHA, model=CHAT,
                  encoder=ENCODER, horizon=16, budget=128000, max_steps=CAP, temperature=0,
                  roots=sites, arms=args.arms, repeats=args.repeats)
    config.update(grading_settings(cfg))
    if old is not None:
        # 首轮完成后允许追加重复和对照组；已有轨迹的工具与参数必须相同。
        if any(config[k] != old[k] for k in config if k not in ("arms", "repeats")):
            raise ValueError("protocol changed; use a separate output directory")
        config["arms"] = list(dict.fromkeys(old["arms"] + args.arms))
        config["repeats"] = max(old["repeats"], args.repeats)
    write_result(cfg, config)
    encoder = DenseEncoder() if "pace" in args.arms else None

    def work(job):
        rep, n, arm = job
        started = monotonic()
        def browser(root, api):
            return Browser(root, api, sites[root], protocol).tools()
        def api_factory():
            api = FullRunAPI.configured()
            api.job = job
            api.output = output
            return api
        result = episode(job, config, dataset, None, encoder, output, browser=browser, api_factory=api_factory)
        print(*result, f"{monotonic()-started:.1f}s", flush=True)

    jobs = []
    for rep in range(1,args.repeats+1):
        for n in range(1,len(dataset)+1):
            for arm in args.arms:
                path = output / f"rep-{rep}/{arm}/row-{n}.json"
                if not path.exists() or "grade" not in json.loads(path.read_text()):
                    jobs.append((rep,n,arm))
    failures = []
    with ThreadPoolExecutor(args.jobs) as pool:
        pending = {pool.submit(work, job):job for job in jobs}
        for task in as_completed(pending):
            try:
                task.result()
            except Exception as exc:
                job = pending[task]
                failures.append({"job":job, "error":str(exc)})
                write_result(output / "incomplete.json", failures)
                print("incomplete", job, str(exc), flush=True)
    write_result(output / "incomplete.json", failures)
    print(report(dataset, config, output))
    if failures:
        raise SystemExit("incomplete API jobs; resume with the same command")


if __name__ == "__main__":
    main()

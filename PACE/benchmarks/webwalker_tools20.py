"""固定题单比较站内导航与 Google + You.com。先完成 ReAct，再按预设条件运行 PACE。"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
from pathlib import Path
from urllib.parse import urlsplit

from pace.records import write_result
from .full_webwalker_preflight import OUT as ARCHIVE
from .google_you import PaperBrowser, credentials
from .you_public import PublicBrowser
from .grading import LEGACY
from .paper_pilot import CAP, ENCODER, DenseEncoder, episode
from .webwalker_full import FullRunAPI
from .webwalker_live import received_page_text
from .webwalkerqa import CACHE, CHAT, DATA_SHA, REVISION, ROOT, load_dataset

PLAN = Path(__file__).with_name("webwalker_tools20.json")
OUT = ROOT / "results/webwalker-tools20"
MIN_CORRECT = 10  # 20 题中至少答对 10 题，距论文 57.9% 的下界不超过 10 个百分点。


def canonical(url):
    p = urlsplit(url)
    return (p.hostname or "").lower().removeprefix("www."), p.port, p.path.rstrip("/"), p.query


def measurements(record, row, new):
    read = set()
    for turn in record["history"]:
        if turn["kind"] != "visit" or turn["observation"].startswith("Tool error:"):
            continue
        if new:
            for page in json.loads(turn["observation"]):
                if page["read"]:
                    read.add(canonical(page["url"]))
        elif received_page_text(turn):
            read.add(canonical(json.loads(turn["action"])["args"]["url"]))
    refs = {canonical(u) for u in row["info"]["source_website"]}
    if not refs:
        raise ValueError("missing reference URLs")
    hits = len(refs & read)
    return dict(correct=record["grade"]["correct"], any_hit=bool(hits), all_hit=hits == len(refs),
                matched=hits, references=len(refs))


def report(rows, numbers):
    summary = {}
    cases = {}
    for label, folder, arm in [("old_react", ARCHIVE, "react"), ("new_react", OUT, "react"),
                               ("old_pace", ARCHIVE, "pace"), ("new_pace", OUT, "pace")]:
        values = []
        for n in numbers:
            path = folder / f"rep-1/{arm}/row-{n}.json"
            if not path.exists() and folder == OUT:
                continue
            record = json.loads(path.read_text())
            if (record["row"], record["arm"], record["repeat"], record["question"]) != (n, arm, 1, rows[n-1]["question"]):
                raise ValueError(f"wrong cohort record {path}")
            if type(record.get("grade", {}).get("correct")) is not bool:
                if folder == OUT:
                    continue
                raise ValueError(f"missing archived verdict {path}")
            result = measurements(record, rows[n-1], folder == OUT)
            values.append(result)
            cases.setdefault(n, {})[label] = result
        summary[label] = dict(graded=len(values), **{key: sum(v[key] for v in values)
                             for key in ("correct", "any_hit", "all_hit", "matched", "references")})
    write_result(OUT / "comparison.json", dict(summary=summary, cases=cases))
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["report", "run"])
    parser.add_argument("--public-you", action="store_true")
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args()
    if args.public_you:
        OUT = ROOT / "results/webwalker-tools20-you-public"
    rows = load_dataset(CACHE)
    selected = json.loads(PLAN.read_text())["selected"]
    numbers = sorted(n for group in selected.values() for n in group)
    if len(set(numbers)) != 20 or any(len(ns) != 10 or any(rows[n-1]["info"]["type"] != kind for n in ns)
                                       for kind, ns in selected.items()):
        raise ValueError("invalid fixed cohort")
    archived = json.loads((ARCHIVE / "config.json").read_text())
    config = dict(dataset=REVISION, sha256=DATA_SHA, model=CHAT, encoder=ENCODER, max_steps=CAP,
                  temperature=0, horizon=16, budget=128000)
    if (any(archived[k] != v for k, v in config.items()) or archived["protocol"] != "full-live-v1"
            or archived.get("grading_version", LEGACY) != LEGACY):
        raise ValueError("archived protocol mismatch")
    config.update(grading_version=LEGACY, protocol="you-public-v1" if args.public_you else "serper-you-contents-v1", rows=numbers, pace_gate=MIN_CORRECT)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cfg = OUT / "config.json"
        if cfg.exists() and json.loads(cfg.read_text()) != config:
            raise ValueError("output configuration mismatch")
        write_result(cfg, config)
        summary = report(rows, numbers)
        if args.command == "report":
            return
        for arm in ("react", "pace"):
            if arm == "pace" and summary["new_react"]["correct"] < MIN_CORRECT:
                print("ReAct 未达到预设门槛，停止。")
                break
            if summary["new_" + arm]["graded"] == len(numbers):
                continue
            keys = (None, None) if args.public_you else credentials()
            browser_type = PublicBrowser if args.public_you else PaperBrowser
            encoder = DenseEncoder() if arm == "pace" else None
            def run_one(n):
                job = (1, n, arm)

                def api_factory():
                    api = FullRunAPI.configured()
                    api.job, api.output = job, OUT
                    return api

                print(episode(job, config, rows, None, encoder, OUT, api_factory=api_factory,
                              browser=lambda root, api: browser_type(api, keys).tools()), flush=True)

            with ThreadPoolExecutor(args.jobs) as pool:
                list(pool.map(run_one, numbers))
            summary = report(rows, numbers)


if __name__ == "__main__":
    main()

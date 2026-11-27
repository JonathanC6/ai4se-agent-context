"""统一题单的五组对照。固定分层抽题，只运行新增单元格。"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
from hashlib import sha256
import json
from pathlib import Path
from shutil import copytree
from urllib.parse import urlsplit

from benchmarks import evidence_v2
from benchmarks.evidence_v2 import COHORT, configuration
from benchmarks.paper_pilot import DenseEncoder
from benchmarks.webwalkerqa import CACHE, CHAT, DATA_SHA, grade, load_dataset
from pace.records import write_result
from .benchmark import api_for
from .public_search import PublicLiteBrowser
from .dag_study import ARMS, DEFAULT as PRIOR, describe, read, run_one
from .replacement_report import render

OUT = PRIOR.with_name("matched20-unified-ddg")
REMOVED = (2, 25, 26, 48, 115, 407)
SEED = "webwalkerqa-unified-20-v1"
MATCH = ("type","lang","difficulty_level","domain")
MAX_ATTEMPTS = 3


def cohort(data):
    calibration = read(Path(evidence_v2.__file__).with_name("evidence_v2_horizon.json"))["observed_steps"]
    excluded = set(COHORT) | set(map(int,calibration)) | {32,42,50}
    mapping = {}
    for old in REMOVED:
        target = data[old-1]
        options = [n for n,row in enumerate(data,1) if n not in excluded
                   and all(row["info"][k]==target["info"][k] for k in MATCH)]
        def order(n):
            site_mismatch = urlsplit(data[n-1]["root_url"]).hostname != urlsplit(target["root_url"]).hostname
            return site_mismatch, sha256(f"{SEED}/{old}/{n}".encode()).hexdigest()
        chosen = min(options,key=order)
        mapping[old] = chosen
        excluded.add(chosen)
    return mapping


def result_file(directory, arm, n):
    if arm in ("pace","dag-pace"):
        return directory / "rep-1" / arm / f"row-{n}.json"
    return directory / arm / f"row-{n}" / "result.json"


def load_scored(directory, arm, n):
    path = result_file(directory, arm, n)
    if path.exists():
        record = read(path)
        if type(record.get("grade",{}).get("correct")) is bool:
            return record
    return None


def make_plan(data):
    before = read(PRIOR/"comparison.json")["rows"]
    missing = {int(n) for arm in ARMS for n,v in before[arm].items() if type(v["correct"]) is not bool}
    if missing != set(REMOVED):
        raise ValueError("prior missing rows differ from the registered cohort")
    replacement = cohort(data)
    rows = sorted(replacement.get(n,n) for n in COHORT)
    counts = Counter(data[n-1]["info"]["type"] for n in rows)
    if counts != {"single_source":10,"multi_source":10} or len(set(rows)) != 20:
        raise ValueError("unbalanced cohort")
    settings = configuration(observe_gateway=True)
    return dict(seed=SEED, matched_fields=list(MATCH), tie_break="same host then sha256(seed/old/new)",
                mapping={str(k):v for k,v in replacement.items()}, rows=rows, arms=list(ARMS),
                retained=sorted(set(COHORT)-missing), fresh=sorted(replacement.values()),
                data_sha256=DATA_SHA, prior_comparison_sha256=sha256((PRIOR/"comparison.json").read_bytes()).hexdigest(),
                model=CHAT, budget=settings["budget"], horizon=settings["horizon"], max_steps=settings["max_steps"],
                grading=settings["grading_version"], search="shared historical query cache; new queries use DuckDuckGo Lite",
                action_protocols={"pace":"reviewed-json-v1","dag-pace":"reviewed-json-v1",
                "react":"recoverable-actions-v2","pace-v2":"recoverable-actions-v2","pace-v2-dag":"recoverable-actions-v2"},
                max_episode_attempts=MAX_ATTEMPTS)


def roles_for(events):
    roles = {}
    for e in events:
        stats = roles.setdefault(e["role"],Counter())
        stats["calls"] += 1
        if "visible_input_estimate" in e:
            stats["metered_calls"] += 1
            stats["visible_lo"] += e["visible_input_estimate"]
            stats["visible_hi"] += e["visible_input_estimate"]
        if "output_text_subwords" in e:
            stats["output_metered_calls"] += 1
            stats["visible_output_subwords"] += e["output_text_subwords"]
    return roles


def collect(out, plan, data):
    before = read(PRIOR/"comparison.json")["rows"]
    rows = {arm:{str(n):before[arm][str(n)] for n in plan["retained"]} for arm in ARMS}
    selected = {}
    attempts = {}
    for directory in sorted(out.glob("attempt-*")):
        path = directory/"usage.jsonl"
        events = {}
        if path.exists():
            for line in path.read_text().splitlines():
                e = json.loads(line)
                _,n,arm = e["job"]
                events.setdefault((arm,n),[]).append(e)
        for n in plan["fresh"]:
            for arm in ARMS:
                record = load_scored(directory,arm,n)
                failure = directory/arm/f"row-{n}"/"failure.json"
                if not (record or failure.exists() or (arm,n) in events):
                    continue
                event_roles = roles_for(events.get((arm,n),[]))
                status = (record["status"] if record else "execution_failed" if failure.exists() else "pending")
                key = f"{arm}/{n}"
                attempts.setdefault(key,[]).append(dict(directory=directory.name,status=status,roles=event_roles))
                if failure.exists() and not record:
                    attempts[key][-1]["failure"] = read(failure)
                if record and key not in selected:
                    selected[key]=directory.name
                    rows[arm][str(n)] = dict(describe(record),roles=event_roles,source=directory.name)
    for n in plan["fresh"]:
        for arm in ARMS:
            key=f"{arm}/{n}"
            status=attempts.get(key,[{"status":"pending"}])[-1]["status"]
            rows[arm].setdefault(str(n),dict(correct=None,status=status))
    comparison=dict(rows=rows,selected=selected,attempts=attempts,cohort=plan["rows"])
    write_result(out/"comparison.json",comparison)
    render(out,plan,comparison,data)
    return selected


def job(n,arm,data,encoder,directory,settings):
    result = run_one(n,arm,data,encoder,directory,settings,browser_class=PublicLiteBrowser)
    path = result_file(directory,arm,n)
    # 已交卷时仅恢复裁判请求。保留求解结果，避免用新一次行动改写答案。
    if path.exists() and not load_scored(directory,arm,n):
        record=read(path)
        judge=api_for(n,arm,directory)
        try:
            record["grade"]=grade(data[n-1],record["answer"],judge,CHAT,settings["grading_version"])
            record["usage"].update(judge.usage)
            write_result(path,record)
            return n,arm,"scored"
        except Exception as exc:
            print("judge retry",n,arm,type(exc).__name__,flush=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("command",choices=("plan","run","report"))
    p.add_argument("--out",type=Path,default=OUT)
    p.add_argument("--jobs",type=int,default=3,choices=range(1,6))
    args=p.parse_args()
    data=load_dataset(CACHE)
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    plan=make_plan(data)
    path=out/"cohort.json"
    if path.exists() and read(path)!=plan:
        raise ValueError("cohort or source comparison changed")
    write_result(path,plan)
    if args.command=="plan":
        print(plan["mapping"])
        return
    if args.command=="report":
        collect(out,plan,data)
        return
    with (out/"run.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        cache=out/"shared-search"
        if not cache.exists():
            copytree(PRIOR/"shared-search",cache)
        encoder=DenseEncoder()
        settings=dict(configuration(observe_gateway=True),action_protocol="reviewed-json-v1")
        selected=collect(out,plan,data)
        for index in range(1,MAX_ATTEMPTS+1):
            directory=out/f"attempt-{index}"
            directory.mkdir(exist_ok=True)
            if not (directory/"shared-search").exists():
                (directory/"shared-search").symlink_to(cache,target_is_directory=True)
            jobs=[]
            for i,n in enumerate(plan["fresh"]):
                for arm in ARMS[i%5:]+ARMS[:i%5]:
                    key=f"{arm}/{n}"
                    rowdir=directory/arm/f"row-{n}"
                    if key not in selected and not (rowdir/"failure.json").exists():
                        jobs.append((n,arm))
            if jobs:
                print("START",index,len(jobs),"episodes",flush=True)
                with ThreadPoolExecutor(args.jobs if index==1 else 1) as pool:
                    fs=[pool.submit(job,n,arm,data,encoder,directory,settings) for n,arm in jobs]
                    for future in as_completed(fs):
                        print("RESULT",*future.result(),flush=True)
            selected=collect(out,plan,data)
            if len(selected)==30:
                break
        print("END",len(selected),"/ 30 new cells scored",flush=True)


if __name__=="__main__":
    main()

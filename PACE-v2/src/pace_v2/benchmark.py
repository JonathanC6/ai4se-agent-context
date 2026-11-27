"""固定 20 道开发题。每题每组一个 episode；原始轨迹与判分分别落盘。"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
from pathlib import Path
from shutil import copytree
from time import monotonic
from benchmarks.evidence_v2 import COHORT, configuration
from benchmarks.grading import LEGACY
from benchmarks.paper_pilot import ASSETS, DenseEncoder
from benchmarks.webwalkerqa import CACHE, CHAT, grade, load_dataset
from benchmarks.usage_meter import add_measurement
from pace.providers.encoding import VisibleWindowCounter, load_count_tokenizer
from pace.records import write_result
from .browser import Browser
from .actions import ActionAPI
from .episode import solve

ROOT=Path(__file__).resolve().parents[2]
DEFAULT=ROOT/"results/matched20-actions-v2"
ARMS=("react","pace-v2")


def config():
    c=configuration(observe_gateway=True)
    return dict(c, arms=list(ARMS),workload="matched20-actions-v2",method="paired",
                action_protocol="recoverable-actions-v2",search_backend="historical-public-then-you-v1",
                reader="shared-archive-multiwindow-v1",max_reviews=2,
                arm_settings={"react":"full-history","pace-v2":"checklist-recent-excerpt-v1"},
                tools={"react":["search","visit","reread","finish"],
                       "pace-v2":["search","visit","reread","finish","glimpse"]})


def api_for(n,arm,out):
    api=ActionAPI.configured()
    api.job,api.output=(1,n,arm),out
    return api


def one(n,arm,row,encoder,out,strategy_factory=None,*,retry_search=False,browser_class=Browser):
    directory=out/arm/f"row-{n}"
    directory.mkdir(parents=True,exist_ok=True)
    final=directory/"result.json"
    checkpoint=directory/"checkpoint.json"
    failure=directory/"failure.json"
    if failure.exists() and not final.exists():
        return n,arm,"previous_execution_failure"
    started=monotonic()
    try:
        if final.exists():
            result=json.loads(final.read_text())
        else:
            if checkpoint.exists():
                raise RuntimeError("interrupted episode retained; no automatic restart")
            api=api_for(n,arm,out)
            browser=browser_class(row["root_url"],api,n,directory,out/"shared-search")
            browser.retry_rate_limits=retry_search
            counter=VisibleWindowCounter(load_count_tokenizer(ASSETS/"tokenizer.json"))
            result=solve(row["question"],row["root_url"],browser,api,counter,encoder,arm,
                         lambda data:write_result(checkpoint,data),
                         strategy=strategy_factory() if strategy_factory else None)
            result.update(row=n,arm=arm,question=row["question"],kind=row["info"]["type"],
                          solver_seconds=monotonic()-started,usage=api.usage)
            write_result(final,result)
        if "grade" not in result:
            judge=api_for(n,arm,out)
            result["grade"]=grade(row,result["answer"],judge,CHAT,LEGACY)
            result["usage"].update(judge.usage)
            write_result(final,result)
        return n,arm,result["status"]
    except Exception as exc:
        write_result(failure,dict(row=n,arm=arm,stage="judge" if final.exists() else "solve",
                                  error=type(exc).__name__,detail=str(exc)[:260]))
        return n,arm,"execution_failed"


def failed_jobs(prior):
    config_before=json.loads((prior/"config.json").read_text())
    current=config()
    for key in current.keys()-{"action_protocol","workload"}:
        if config_before.get(key)!=current[key]:
            raise ValueError(f"previous run uses a different {key}")
    rows=json.loads((prior/"comparison.json").read_text())["arms"]
    failed=[]
    for n in COHORT:
        for arm in ARMS:
            status=rows[arm]["rows"][str(n)]["status"]
            if status=="pending":
                raise ValueError("previous run is incomplete")
            if status=="execution_failed":
                failed.append((n,arm))
    return failed


def collect(out, prior=None):
    retries=set(failed_jobs(prior)) if prior else set()
    records={}
    for arm in ARMS:
        counts=Counter()
        rows={}
        for n in COHORT:
            source=prior if prior and (n,arm) not in retries else out
            directory=source/arm/f"row-{n}"
            p=directory/"result.json"
            row=json.loads(p.read_text()) if p.exists() else {}
            grade_obj=row.get("grade",{})
            valid=type(grade_obj.get("correct")) is bool
            if not valid and (directory/"checkpoint.json").exists() and not row:
                row=json.loads((directory/"checkpoint.json").read_text())
            status=(row["status"] if valid else "execution_failed" if (directory/"failure.json").exists() else "pending")
            counts[status]+=1
            if valid:
                counts["scored"]+=1
                counts["correct"]+=grade_obj["correct"]
            steps=row.get("steps",[])
            reviews=[s["recovery"] for s in steps if "recovery" in s]
            item=dict(status=status,correct=grade_obj.get("correct"),steps=len(steps),drafts=len(row.get("drafts",[])),
                      run=source.name,submission=row.get("submission_state"),
                      reviews=len(reviews),tool_ok=sum(v["tool_ok"] for v in reviews),
                      new_bound=sum(v["new_bound_evidence"] for v in reviews),
                      recovered=sum(v["finding"]=="resolved" for v in reviews),
                      recent_compaction=sum(bool((s.get("window") or {}).get("recent_excerpt_chars")) for s in steps))
            for k in ("reviews","tool_ok","new_bound","recovered","recent_compaction"):
                counts[k]+=item[k]
            rows[n]=item
        records[arm]=dict(counts=dict(counts),rows=rows,tokens_by_role={},selected_tokens=0,rerun_tokens=0,
                          selected_metering_by_role={})
    for source in ([prior,out] if prior else [out]):
        ledger=source/"usage.jsonl"
        if not ledger.exists():
            continue
        for line in ledger.read_text().splitlines():
            e=json.loads(line)
            _,n,arm=e["job"]
            entry=records[arm]
            role=e["role"]; amounts=entry["tokens_by_role"]
            amounts[role]=amounts.get(role,0)+e["total_tokens"]
            if source==out or (n,arm) not in retries:
                entry["selected_tokens"]+=e["total_tokens"]
                add_measurement(entry["selected_metering_by_role"].setdefault(role,{}),e)
            if prior and source==out:
                entry["rerun_tokens"]+=e["total_tokens"]
    for entry in records.values():
        c=entry["counts"]
        entry["accuracy_on_20"]=(c.get("correct",0)/len(COHORT) if c.get("pending",0)==0 else None)
    pairs={}
    for n in COHORT:
        a,b=(records[k]["rows"][n] for k in ARMS)
        if a["correct"] is not None and b["correct"] is not None:
            label=("right" if a["correct"] else "wrong")+"/"+("right" if b["correct"] else "wrong")
        else:
            label="unpaired"
        pairs.setdefault(label,[]).append(n)
    write_result(out/"comparison.json",dict(arms=records,react_vs_pace_v2=pairs))
    return {k:v["counts"] for k,v in records.items()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("run","report"))
    parser.add_argument("--out",type=Path,default=DEFAULT)
    parser.add_argument("--jobs",type=int,default=3)
    parser.add_argument("--retry-failures-from",type=Path,help="仅补跑该次归档的执行异常；其他成绩复用")
    args=parser.parse_args()
    out=args.out.resolve()
    prior=args.retry_failures_from.resolve() if args.retry_failures_from else None
    if prior==out:
        parser.error("choose a separate output directory for the rerun")
    p=out/"config.json"
    if args.command=="report":
        if not p.exists():
            parser.error("run configuration missing")
        existing=json.loads(p.read_text())
        if existing.get("retry_jobs") is not None and not prior:
            parser.error("pass the original run with --retry-failures-from")
        if prior and existing.get("retry_jobs")!=[list(j) for j in failed_jobs(prior)]:
            parser.error("prior run does not match the selected jobs")
        print(collect(out,prior),flush=True)
        return
    if not 1<=args.jobs<=8:
        parser.error("choose 1 to 8 workers")
    out.mkdir(parents=True,exist_ok=True)
    with (out/"run.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        c=config()
        jobs=[(n,arm) for i,n in enumerate(COHORT) for arm in (ARMS if i%2==0 else ARMS[::-1])]
        if prior:
            jobs=failed_jobs(prior)
            c.update(retry_jobs=[list(j) for j in jobs],prior_run=prior.name)
        if p.exists() and json.loads(p.read_text())!=c:
            raise ValueError("configuration mismatch")
        write_result(p,c)
        if prior and (prior/"shared-search").is_dir() and not (out/"shared-search").exists():
            copytree(prior/"shared-search",out/"shared-search")
        api_for(COHORT[0],ARMS[0],out)
        data=load_dataset(CACHE)
        encoder=DenseEncoder()
        # 同题两组交错派发，共享同查询排名和页面缓存。
        print("START",len(jobs),"episodes",flush=True)
        with ThreadPoolExecutor(args.jobs) as pool:
            futures=[pool.submit(one,n,arm,data[n-1],encoder,out) for n,arm in jobs]
            for future in as_completed(futures):
                print("RESULT",*future.result(),flush=True)
        print("END",collect(out,prior),flush=True)


if __name__=="__main__":
    main()

"""在独立部署目录中通过 SSH 标准输入接收本轮凭据并启动 nohup。"""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--study", choices=("actions","dag","unified"), default="actions")
    parser.add_argument("--repair-rate-limits",action="store_true")
    args=parser.parse_args()
    os.umask(0o077)
    project=Path(__file__).resolve().parents[1]
    root=project.parent
    module, folder = {
        "actions": ("pace_v2.benchmark", "matched20-actions-v2"),
        "dag": ("pace_v2.dag_study", "dag-matched20"),
        "unified": ("pace_v2.replacement_study", "matched20-unified-ddg"),
    }[args.study]
    out=project/"results"/folder
    out.mkdir(parents=True,exist_ok=True)
    repair=args.repair_rate_limits
    if repair and (args.study!="dag" or not (out/"config.json").exists()):
        raise SystemExit("missing DAG study to repair")
    if not repair and ((out/"config.json").exists() or (out/"pid").exists()):
        raise SystemExit("run already exists")
    key=sys.stdin.readline().strip()
    if not key:
        raise SystemExit("missing process credential")
    env=dict(os.environ,PACE_API_KEY=key,PACE_BASE_URL="https://api.labhuan.com/v1",
             PYTHONPATH=os.pathsep.join(str(p) for p in (project/"src",root/"PACE/src",root/"PACE",root/"DAG-PACE/src")),
             PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1")
    prefix="rate-retry" if repair else "run"
    with (out/(prefix+".log")).open("x") as log:
        job=subprocess.Popen(["nohup",str(root/".venv/bin/python"),"-u","-m",module,"repair-rate-limits" if repair else "run",
                              "--out",str(out),"--jobs","3"],cwd=root,env=env,stdin=subprocess.DEVNULL,
                             stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
    (out/("rate-retry.pid" if repair else "pid")).write_text(str(job.pid)+"\n")
    print("started PID",job.pid,flush=True)


if __name__=="__main__":
    main()

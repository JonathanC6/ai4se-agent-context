"""Run a PACE baseline on the WebWalkerQA main split using a frozen website."""
import argparse
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

from pace.agent import run
from pace.memory import Memory
from pace.policy import Settings
from pace.providers import API, ProviderError, RemoteEncoder, ReplyFormatError, Utf8Counter
from pace.records import write_result
from .grading import LEGACY, SEMANTIC, LEGACY_PROMPT, SEMANTIC_PROMPT, grading_settings, standalone_date
from .webwalker_snapshot import fetch, prepare_site, site_tools, snapshot_digest


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/webwalkerqa"
REVISION = "c7ab3329a2a4a35ca569fdca369b61a3d1787e5b"
DATA_SHA = "cbe95d9de714ef52fe4a9ddf160dfab462407cb1ba526f1c31b4305ca32c34cb"
DATA_URL = f"https://huggingface.co/datasets/callanwu/WebWalkerQA/resolve/{REVISION}/data/main-00000-of-00001.jsonl"
PILOT_SITE = "https://2023.aclweb.org/"
CHAT = "claude-sonnet-4-6"
EMBED = "GLM-Embedding-3"


def load_dataset(cache):
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "main.jsonl"
    raw = path.read_bytes() if path.exists() else fetch(DATA_URL)
    if hashlib.sha256(raw).hexdigest() != DATA_SHA:
        raise ValueError("main split checksum differs from the pinned release")
    if not path.exists():
        path.write_bytes(raw)
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def select_rows(rows, root, numbers):
    site_rows = {n: row for n, row in enumerate(rows, 1) if row["root_url"] == root}
    if numbers is None:
        first_by_type = {}
        for n, row in site_rows.items():
            first_by_type.setdefault(row["info"]["type"], n)
        if not {"single_source", "multi_source"} <= first_by_type.keys():
            raise ValueError("root lacks a single- or multi-source item, select explicit --rows")
        return [first_by_type["single_source"], first_by_type["multi_source"]]
    if len(set(numbers)) != len(numbers):
        raise ValueError("duplicate row numbers")
    for n in numbers:
        if n not in site_rows:
            raise ValueError(f"row {n} does not belong to this snapshot")
    return numbers


def benchmark_chat(api, model, messages, purpose):
    try:
        return api.chat(model, messages, purpose, max_tokens=1600)
    except ReplyFormatError:
        print(f"  {purpose}: retrying malformed JSON", flush=True)
        system = dict(messages[0])
        system["content"] += "\nEmit only one valid JSON object. No Markdown or preamble. Keep strings concise."
        return api.chat(model, [system, *messages[1:]], purpose, max_tokens=2400)


def solve(question, root, tools, api, config, strategy=None):
    start = time.monotonic()
    settings = Settings(config["horizon"], budget=config["budget"])
    encode = RemoteEncoder(api, config["embedding"], 8192)

    def actor(messages):
        reply = benchmark_chat(api, config["actor"], messages, "actor")
        print(f"  actor request {api.usage['actor']['requests']}: {reply.get('tool')}", flush=True)
        return reply

    prompt = (f"Website: {root}\nQuestion: {question}\nUse search and visit to check the website "
              "before answering. If the pages lack the requested information, state what is missing.")
    with Memory(encode, lambda text: api.summarize(config["summary"], text)) as memory:
        result = run(prompt, tools, actor, memory, settings, Utf8Counter(), config["max_steps"],
                     lambda: api.last_input_tokens.get("actor"), strategy=strategy)
    result["solver_seconds"] = time.monotonic() - start  # Includes outstanding background summaries.
    result["history"] = saved_history(memory)
    result["usage"] = {k: dict(v) for k, v in api.usage.items()}
    return result


def saved_history(memory):
    history = []
    for chunk in memory.chunks:
        summary, state = chunk.summary_snapshot()
        history.append({
            "id": chunk.id, **asdict(chunk.turn), "summary_state": state,
            "summaries": asdict(summary) if summary else None,
        })
    return history


def grade(row, answer, api, model, version=SEMANTIC):
    if version not in (LEGACY, SEMANTIC):
        raise ValueError("unknown grading version")
    if not answer or not answer.strip():
        return {"correct": False, "reason": "No final answer within the episode limits.", "version": version}
    if version == SEMANTIC:
        ref_date = standalone_date(row["answer"])
        if ref_date is not None and ref_date == standalone_date(answer):
            return {"correct": True, "reason": "Equivalent complete calendar dates.",
                    "version": version, "method": "date"}
    prompt = LEGACY_PROMPT if version == LEGACY else SEMANTIC_PROMPT
    fields = {"question": row["question"], "reference": row["answer"], "prediction": answer}
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(fields, ensure_ascii=False)},
    ]
    obj = benchmark_chat(api, model, messages, "judge")
    if type(obj.get("correct")) is not bool:
        raise ValueError("judge response missing boolean verdict")
    return {**obj, "version": version, "method": "judge"}


def run_case(n, row, root, tools, config, out, strategy=None):
    path = out / f"row-{n}.json"
    if path.exists():
        result = json.loads(path.read_text())
    else:
        api = API.configured()
        started = time.monotonic()
        try:
            result = solve(row["question"], root, tools, api, config, strategy)
        except ProviderError as exc:
            write_result(out / f"interrupted-{n}-{time.time_ns()}.json",
                         {"error": str(exc), "seconds": time.monotonic() - started, "usage": api.usage})
            raise
        result.update(row=n, question=row["question"], kind=row["info"]["type"])
        write_result(path, result)  # Solving and paid judging can resume independently.
    if "grade" not in result:
        judge = API.configured()
        start = time.monotonic()
        result["grade"] = grade(row, result["answer"], judge, config["judge"], config.get("grading_version", LEGACY))
        result["judge_seconds"] = time.monotonic() - start
        result["usage"].update({k: dict(v) for k, v in judge.usage.items()})
        result["reference"] = row["answer"]
        result["reference_urls"] = row["info"]["source_website"]
        write_result(path, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("--root", default=PILOT_SITE)
    parser.add_argument("--snapshot", type=Path, default=CACHE / "acl2023.json")
    parser.add_argument("--rows", type=int, nargs="+", help="one-based main split row numbers; same root")
    parser.add_argument("--out", type=Path, default=ROOT / "results/webwalkerqa-baseline")
    parser.add_argument("--max-steps", type=int, default=16)
    args = parser.parse_args()
    if args.max_steps < 1:
        parser.error("--max-steps must be positive")
    rows = load_dataset(CACHE)
    if args.action == "prepare":
        if args.snapshot.exists():
            snap = json.loads(args.snapshot.read_text())
            if snap["root"] != args.root or snapshot_digest(snap["pages"]) != snap["sha256"]:
                raise ValueError("existing snapshot has a different root or invalid digest")
        else:
            snap = prepare_site(args.root, args.snapshot)
        print(len(snap["pages"]), "pages", len(snap["errors"]), "errors", snap["sha256"])
        return
    snap = json.loads(args.snapshot.read_text())
    if snap["root"] != args.root:
        raise ValueError("snapshot root mismatch")
    tools = site_tools(snap)
    numbers = select_rows(rows, args.root, args.rows)
    config = {
        "protocol": 2, "dataset_revision": REVISION, "dataset_sha256": DATA_SHA,
        "snapshot_sha256": snap["sha256"], "root": args.root, "rows": numbers,
        "actor": CHAT, "summary": CHAT, "embedding": EMBED, "judge": CHAT,
        "budget": 128000, "horizon": 16, "max_steps": args.max_steps,
        "counter": "utf8 + provider feedback",
    }
    cfg_file = args.out / "config.json"
    config.update(grading_settings(cfg_file))
    if cfg_file.exists() and json.loads(cfg_file.read_text()) != config:
        raise ValueError("output belongs to a different run configuration")
    write_result(cfg_file, config)
    for n in numbers:
        row = rows[n - 1]
        print(f"Row {n} ({row['info']['type']}): {row['question']}", flush=True)
        result = run_case(n, row, args.root, tools, config, args.out)
        fields = ("row", "status", "answer", "grade", "solver_seconds", "judge_seconds", "usage")
        print(json.dumps({k: result[k] for k in fields}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

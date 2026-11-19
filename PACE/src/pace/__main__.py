"""Command-line entry points for an offline smoke test and a model-backed episode."""
import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

from .agent import run, snapshot_tools
from .memory import Memory, Summaries
from .policy import Settings, p95
from .providers import API, BgeEncoder, ChatTokens, ProviderError, RemoteEncoder, Utf8Counter, demo_encode
from .records import write_result


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/workshop.json"


def demo_actor():
    moves = iter([("search", {"query": "Alder workshop"}), ("visit", {"page": "index"}),
                  ("visit", {"page": "committee"}), ("visit", {"page": "registrar"})])
    restored = False

    def act(messages):
        nonlocal restored
        move = next(moves, None)
        if move:
            return {"tool": move[0], "args": move[1]}
        if not restored and 'glimpse {"ids"' in messages[0]["content"]:
            restored = True
            return {"tool": "glimpse", "args": {"ids": [3]}}
        text = messages[-1]["content"]
        name = re.search(r"names the chair as \w+ (\w+)", text)
        date = re.search(r"final registration date is ([0-9-]+)", text)
        answer = f"{name[1]} | {date[1]}" if name and date else "unknown"
        return {"tool": "finish", "args": {"answer": answer}}
    return act


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("demo", "run"))
    parser.add_argument("--task", type=Path, default=EXAMPLE, help="JSON with question and snapshot pages")
    parser.add_argument("--output", type=Path)
    horizon_arg = parser.add_mutually_exclusive_group()
    horizon_arg.add_argument("--horizon", type=int, help="T_max for a new dataset")
    horizon_arg.add_argument("--validation-lengths", type=Path, help="JSON array of validation episode lengths")
    parser.add_argument("--budget", type=int, default=128000)
    parser.add_argument("--max-steps", type=int, default=16)
    parser.add_argument("--temperature", type=float, default=0.3, help="retrieval softmax temperature")
    parser.add_argument("--adaptation", type=float, default=0.5)
    parser.add_argument("--no-multigran", action="store_true")
    parser.add_argument("--no-glimpse", action="store_true")
    parser.add_argument("--actor", default="claude-sonnet-4-6")
    parser.add_argument("--summary-model", default="claude-sonnet-4-6")
    parser.add_argument("--encoder", choices=("bge", "api"), default="bge")
    parser.add_argument("--bge-model", default="BAAI/bge-m3")
    parser.add_argument("--embedding-model", default="GLM-Embedding-3")
    parser.add_argument("--embedding-tokenizer", help="tokenizer for hosted embeddings (otherwise cap UTF-8 bytes)")
    parser.add_argument("--embedding-limit", type=int, default=8192)
    parser.add_argument("--chat-tokenizer", help="HF tokenizer with chat template, local path, or utf8 for proxy counts")
    args = parser.parse_args()
    if args.mode == "demo" and args.task != EXAMPLE:
        parser.error("the scripted demo uses the included workshop. Use run for a custom task.")
    if args.validation_lengths:
        horizon = p95(json.loads(args.validation_lengths.read_text()))
    elif args.horizon is not None:
        horizon = args.horizon
    elif args.task == EXAMPLE:
        horizon = 16
    else:
        parser.error("provide --validation-lengths or --horizon for this task")
    cfg = Settings(horizon, args.budget, temperature=args.temperature, adaptation=args.adaptation,
                   multi_level=not args.no_multigran, glimpse_limit=0 if args.no_glimpse else 3)
    task = json.loads(args.task.read_text())
    tools = snapshot_tools(task["pages"])
    api = None
    if args.mode == "demo":
        encode, counter, actor = demo_encode, Utf8Counter(), demo_actor()
        def summarize(full):
            return Summaries(full[:180], full.splitlines()[1][:80])
        models = {"actor": "scripted", "encoder": "word-hash", "summary": "extractive", "counter": "utf8"}
    else:
        api = API.configured()
        if args.encoder == "bge":
            encode = BgeEncoder(args.bge_model)
        else:
            encode = RemoteEncoder(api, args.embedding_model, args.embedding_limit, args.embedding_tokenizer)
        local_tokenizer = ROOT / ".cache/deepseek-v3.1"
        tokenizer = args.chat_tokenizer
        if not tokenizer:
            if args.actor == "DeepSeek-V3.1":
                tokenizer = str(local_tokenizer) if local_tokenizer.is_dir() else "deepseek-ai/DeepSeek-V3.1"
            else:
                tokenizer = "utf8"
        counter = Utf8Counter() if tokenizer == "utf8" else ChatTokens(tokenizer)
        def actor(messages):
            return api.chat(args.actor, messages, "actor")
        def summarize(full):
            return api.summarize(args.summary_model, full)
        models = {"actor": args.actor, "encoder": args.bge_model if args.encoder == "bge" else args.embedding_model,
                  "encoder_backend": args.encoder, "summary": args.summary_model, "counter": tokenizer,
                  "endpoint": api.base, "embedding_input_limit": 8192 if args.encoder == "bge" else args.embedding_limit,
                  "embedding_input_unit": "tokens" if args.encoder == "bge" or args.embedding_tokenizer else "utf8_bytes"}
    with Memory(encode, summarize) as memory:
        usage_for_actor = (lambda: api.last_input_tokens.get("actor")) if api else None
        result = run(task["question"], tools, actor, memory, cfg, counter, args.max_steps, usage_for_actor)
    result["history"] = []
    for c in memory.chunks:
        summary, state = c.summary_snapshot()
        result["history"].append({"id": c.id, **asdict(c.turn), "summary_state": state,
                                  "summaries": asdict(summary) if summary else None})
    result.update(task=task["id"], settings=asdict(cfg), models=models, max_steps=args.max_steps,
                  usage=api.usage if api else {}, total_decision_tokens=sum(
                      s.get("input_tokens_actual", s["input_tokens_estimate"]) for s in result["steps"]))
    if "reference" in task:
        result["exact_match"] = (result["answer"] or "").strip().casefold() == task["reference"].strip().casefold()
    if args.output:
        write_result(args.output, result)
    print(json.dumps({k: result[k] for k in ("status", "answer", "exact_match", "glimpse_calls",
                                              "total_decision_tokens", "usage", "error") if k in result},
                     ensure_ascii=False, indent=2))
    return 0 if result["status"] == "finished" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ProviderError, ValueError, OSError) as exc:
        sys.exit(str(exc))

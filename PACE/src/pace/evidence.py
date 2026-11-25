"""已压缩交互和原始网页分别处理；仅使用当前题已经取得的观察。"""
import json

from .policy import Level


def source_args(memory, args):
    """定向 glimpse 只可重读指定 visit 块实际见过的来源。"""
    ids = args.get("ids")
    if not isinstance(ids, list) or len(ids) != 1 or type(ids[0]) is not int or not 1 <= ids[0] <= len(memory.chunks):
        raise ValueError("targeted glimpse needs exactly one historical chunk ID")
    turn = memory.chunks[ids[0]-1].turn
    if turn.kind != "visit":
        raise ValueError("targeted glimpse requires a visit chunk")
    try:
        rows = json.loads(turn.observation)
    except ValueError:
        rows = []
    sources = [r["source_id"] for r in rows if isinstance(r, dict) and r.get("read") and r.get("source_id")]
    sid = args.get("source_id", sources[0] if len(sources) == 1 else None)
    if sid not in sources:
        raise ValueError("choose a source_id from this successful visit")
    return {k: args[k] for k in ("goal", "offset", "find") if k in args} | {"source_id": sid}


def review_request(args, context, glimpse_limit):
    missing = args.get("missing_facts")
    if not isinstance(missing, list):
        return None
    goal = "; ".join(s.strip() for s in missing if isinstance(s, str) and s.strip())
    if not goal:
        return None
    if isinstance(args.get("source_id"), str) and args["source_id"]:
        return "reread", {"source_id": args["source_id"], "goal": goal}
    chunk_id = args.get("chunk_id")
    if glimpse_limit and type(chunk_id) is int and any(
        r.chunk.id == chunk_id and r.shown < Level.FULL for r in context.selections
    ):
        return "glimpse", {"ids": [chunk_id]}
    return None

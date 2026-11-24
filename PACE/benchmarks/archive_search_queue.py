"""供外部网页搜索客户端读取 agent 的原查询、提交搜索结果。"""
import argparse
import json
import sys
from .archive_reader import BASE
from pace.records import write_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["pending", "answer"])
    parser.add_argument("--cdx", action="store_true")
    args = parser.parse_args()
    directory = BASE.with_name(BASE.name + "-cdx") if args.cdx else BASE
    spool = directory / "search"
    if args.action == "pending":
        pending = {}
        for p in sorted(spool.glob("*.query.json"), key=lambda f:f.stat().st_mtime):
            key = p.name.split("-", 1)[1].split(".")[0]
            if not (spool / f"{key}.result.json").exists():
                pending[key] = json.loads(p.read_text())["query"]
        print(json.dumps(pending, ensure_ascii=False))
        return
    import hashlib
    for result in json.load(sys.stdin):
        key = hashlib.sha256(result["query"].encode()).hexdigest()
        if not list(spool.glob(f"*-{key}.query.json")):
            raise ValueError("unknown query")
        write_result(spool / f"{key}.result.json",result)


if __name__ == "__main__":
    main()

"""核对完整 main 题单、既有快照覆盖情况及公开站点入口的可达性。"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from time import monotonic
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pace.records import write_result
from .paper_pilot import address
from .webwalker_snapshot import USER_AGENT, snapshot_digest
from .webwalkerqa import CACHE, DATA_SHA, REVISION, ROOT, load_dataset

OUT = ROOT / "results/webwalkerqa-full"


def probe(root):
    start = monotonic()
    try:
        req = Request(root, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=12) as response:
            status = response.status
            sample = response.read(8192)
            result = {"status": status, "url": response.geturl(),
                      "content_type": response.headers.get_content_type(), "bytes_sampled": len(sample)}
    except (OSError, ValueError) as exc:
        result = {"status": exc.code if isinstance(exc, HTTPError) else None, "error": str(exc)}
    return {**result, "seconds": round(monotonic() - start, 2)}


def main():
    dataset = load_dataset(CACHE)
    roots = sorted({r["root_url"] for r in dataset})
    sites = {}
    for wave in ("paired20", "additional20"):
        files = json.loads((ROOT / f"benchmarks/{wave}.json").read_text())["snapshots"]
        for root, filename in files.items():
            if root not in sites:
                snap = json.loads((CACHE / filename).read_text())
                if snapshot_digest(snap["pages"]) != snap["sha256"]:
                    raise ValueError(f"snapshot digest mismatch for {root}")
                sites[root] = {address(p["url"]) for p in snap["pages"]}
    with ThreadPoolExecutor(8) as pool:
        probes = dict(zip(roots, pool.map(probe, roots)))
    # 标注来源仅用于事后覆盖率核查，不进入运行题单。
    indexed = [r for r in dataset if r["root_url"] in sites]
    covered = sum(all(address(u) in sites[r["root_url"]] for u in r["info"]["source_website"])
                  for r in indexed)
    counts = Counter(r["info"]["type"] for r in dataset)
    ok_roots = {u for u, v in probes.items() if v.get("bytes_sampled", 0)}
    report = {"revision": REVISION, "sha256": DATA_SHA, "questions": len(dataset), "types": counts,
              "roots": len(roots), "cached_roots": len(sites), "cached_questions": len(indexed),
              "cached_reference_complete": covered, "responding_roots": len(ok_roots),
              "responding_root_questions": sum(r["root_url"] in ok_roots for r in dataset),
              "probes": probes}
    write_result(OUT / "preflight.json", report)
    print({k:v for k,v in report.items() if k != "probes"})


if __name__ == "__main__":
    main()

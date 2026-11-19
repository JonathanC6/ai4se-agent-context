"""选择课程方案中的 B/C 组，题单与评测器由 PACE 提供。"""
import sys
from functools import partial
from pathlib import Path

from benchmarks.paired import main
from dag_pace.strategy import DependencyStrategy

if __name__ == "__main__":
    if sys.argv[1:2] not in (["dag"], ["dag-anchor"]):
        raise SystemExit("Usage: ablate.py {dag|dag-anchor} [--plan FILE] [--out DIR]")
    variant = sys.argv.pop(1)
    strategy = partial(DependencyStrategy, anchors=variant == "dag-anchor", supersedes=False)
    main(variant, strategy, Path(__file__).resolve().parents[1] / "results" / variant / "first20")

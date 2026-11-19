"""运行依赖增强组，沿用基线的任务和评分器。"""
from pathlib import Path

from benchmarks.paired import main
from dag_pace.strategy import DependencyStrategy

if __name__ == "__main__":
    main("dag-pace", DependencyStrategy, Path(__file__).resolve().parents[1] / "results/paired20")

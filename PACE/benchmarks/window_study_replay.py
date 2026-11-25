"""在相同的历史、余弦与摘要就绪状态下，只切换压力公式。"""
import argparse
from dataclasses import dataclass, replace
import json
from math import sqrt
from pathlib import Path

from dag_pace.strategy import DependencyStrategy
from pace.agent import instructions
from pace.context import BudgetExceeded, Builder
from pace.memory import Summaries, Turn
from pace.policy import Settings
from pace.providers.encoding import VisibleWindowCounter, load_count_tokenizer
from pace.records import write_result
from .paper_pilot import ASSETS, question_prompt
from .research20 import read
from .research_browser import ResearchBrowser
from .webwalkerqa import CACHE, load_dataset
from .window_study import OUT


@dataclass
class RecordedChunk:
    id: int
    turn: Turn
    full: str
    summaries: Summaries | None
    state: str = "pending"
    key: tuple = ()

    def summary_snapshot(self):
        return (self.summaries if self.state == "ready" else None), self.state


class RecordedHistory:
    def __init__(self):
        self.chunks = []

    @staticmethod
    def encode(_query):
        # 只复原余弦：固定单位查询向量 (1, 0)，与下面的单位键内积恰为记录值。
        return (1.0, 0.0)

    def prepare(self, trace):
        for shown in trace["chunks"]:
            chunk = self.chunks[shown["id"] - 1]
            chunk.state = shown["summaries"]
            if chunk.state == "ready" and chunk.summaries is None:
                raise ValueError("missing historical summary")
            cosine = shown["cos"]
            if cosine is not None:
                chunk.key = (cosine, sqrt(max(0.0, 1.0 - cosine * cosine)))

    def append(self, row):
        turn = Turn(row["thought"], row["action"], row["observation"], row["kind"])
        summary = Summaries(**row["summaries"]) if row["summaries"] else None
        self.chunks.append(RecordedChunk(row["id"], turn, turn.text(), summary))


def replay(record, dataset_row, folder, config, counter):
    arm = record["arm"]
    mode = config["pressure_mode"]
    settings = Settings(config["horizon"], budget=config["budget"], pressure_mode=mode)
    tools = ResearchBrowser(dataset_row["root_url"], None, record["row"], folder).tools()
    system = instructions(tools, settings.glimpse_limit)
    if arm == "dag-pace":
        system += "\n" + DependencyStrategy().instructions
    query = question_prompt(dataset_row["root_url"], dataset_row["question"])
    memory = RecordedHistory()

    def builder(cfg):
        strategy = DependencyStrategy() if arm == "dag-pace" else None
        return Builder(system, query, memory, cfg, counter, strategy, trace_window=True)

    original = builder(settings)
    alternative = builder(replace(settings, pressure_mode="window" if mode == "max" else "max"))
    accepted = len(record["history"]) + int(record["status"] == "finished")
    changed = []
    counterfactual_stop = None
    size_delta = 0
    compared = 0
    for step in record["steps"][:accepted]:
        n = step["step"]
        memory.prepare(step)
        observed = original.build()
        ids = [s.chunk.id for s in observed.selections]
        original_levels = [s.shown.name for s in observed.selections]
        if (ids != [s["id"] for s in step["chunks"]] or
                original_levels != [s["shown"] for s in step["chunks"]] or
                observed.tokens != step["window"]["organized_input_estimate"] or
                abs(observed.pressure - step["pressure"]) > 1e-10):
            raise ValueError(f"original replay mismatch: {arm} row {record['row']} step {n}")

        # 如果历史决策成功经过格式重试，固定该次附加的系统提示和相应预算检查。
        extra = step["input_tokens_estimate"] - observed.tokens
        original.previous_tokens = step["input_tokens_estimate"]
        if extra < 0:
            raise ValueError("unexpected decision token count")
        if counterfactual_stop is None:
            try:
                new = alternative.build()
            except BudgetExceeded:
                counterfactual_stop = n
            else:
                if [s.chunk.id for s in new.selections] != ids:
                    raise ValueError("the fixed history no longer has the same visible chunk IDs")
                if new.tokens + extra > settings.budget:
                    counterfactual_stop = n
                else:
                    alternative.previous_tokens = new.tokens + extra
                    compared += 1
                    size_delta += new.tokens - observed.tokens
                    changes = [
                        [s.chunk.id, prior, s.shown.name] for s, prior in zip(new.selections, original_levels)
                        if s.shown.name != prior
                    ]
                    if changes:
                        changed.append(dict(step=n, chunks=changes, visible_delta=new.tokens - observed.tokens))
        if n <= len(record["history"]):
            turn = record["history"][n - 1]
            memory.append(turn)
            if original.strategy:
                failed = turn["observation"].startswith("Tool error:")
                for b in (original, alternative):
                    if b.strategy.record(n, step["action"], set(ids), failed) != step["metadata"]:
                        raise ValueError("DAG metadata differs from the recorded trajectory")
    return dict(compared_steps=compared, executed_original_steps=accepted, changed=changed,
                visible_delta=size_delta, alternative_local_stop_step=counterfactual_stop)


def run(results, groups):
    data = load_dataset(CACHE)
    counter = VisibleWindowCounter(load_count_tokenizer(ASSETS / "tokenizer.json"))
    output = {}
    for group in groups:
        folder = results / group
        config = read(folder / "config.json")
        arm, = config["arms"]
        if arm not in ("pace", "dag-pace") or config["compression_start_ratio"] is not None:
            raise ValueError("select a PACE or DAG-PACE group without a delayed gate")
        rows = {}
        for n in config["rows"]:
            r = read(folder / f"rep-1/{arm}/row-{n}.json")
            if r["row"] != n or r["question"] != data[n - 1]["question"] or "grade" not in r:
                raise ValueError(f"incomplete or mismatched record for {group} row {n}")
            rows[n] = replay(r, data[n - 1], folder, config, counter)
        summary = dict(compared_steps=sum(r["compared_steps"] for r in rows.values()),
                       changed_steps=sum(len(r["changed"]) for r in rows.values()),
                       changed_questions=sum(bool(r["changed"]) for r in rows.values()),
                       visible_delta=sum(r["visible_delta"] for r in rows.values()),
                       earlier_stops=sum(r["alternative_local_stop_step"] is not None for r in rows.values()))
        output[group] = dict(summary=summary, rows=rows)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=OUT)
    parser.add_argument("--groups", nargs="+", choices=("pace", "dag-pace", "pace-window", "dag-pace-window"),
                        default=["pace", "dag-pace"])
    parser.add_argument("--out", type=Path, help="保存逐题、逐块的差异")
    args = parser.parse_args()
    result = run(args.results, args.groups)
    if args.out:
        write_result(args.out, result)
    print(json.dumps({k: v["summary"] for k, v in result.items()}, indent=2))


if __name__ == "__main__":
    main()

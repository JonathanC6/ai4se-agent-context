"""固定动作、观察和上一轮输入用量，回放压力公式对展示粒度的影响。无需 API。"""
from collections import Counter
import argparse
from dataclasses import replace
import json

from pace.agent import instructions
from pace.context import Builder, Selection
from pace.memory import Chunk, Turn
from pace.policy import Level, Settings
from pace.providers import Utf8Counter
from .paper_pilot import question_prompt
from .webwalker_budget20 import BASE
from .webwalker_dynamic20 import DynamicBrowser
from .webwalkerqa import CACHE, load_dataset


def fit_step(step, history, builder, pressure=None):
    rows = []
    bounds = builder.settings.boundaries(step["pressure"] if pressure is None else pressure)
    for c in step["chunks"]:
        h = history[c["id"] - 1]
        turn = Turn(h["thought"], h["action"], h["observation"], h["kind"])
        full = turn.text()
        versions = {Level.FULL: full, Level.PLACEHOLDER: ""}
        if c["summaries"] == "ready":
            versions.update({Level.DETAILED: h["summaries"]["detailed"], Level.BRIEF: h["summaries"]["brief"]})
        level = builder.settings.level(c["weight"], bounds) if c["weight"] is not None else Level.FULL
        shown = level if level in versions else Level.FULL
        chunk = Chunk(c["id"], turn, full, (), None)
        rows.append(Selection(chunk, versions, level, shown, c["cos"], c["weight"], c["summaries"]))
    _, size = builder.fit(rows, max(0, len(rows) - builder.settings.recent))
    return [r.shown.name for r in rows], size


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("quadratic", "occupancy"), default="quadratic")
    args = parser.parse_args()
    folder = BASE / "pace"
    config = json.loads((folder / "config.json").read_text())
    cfg = Settings(config["horizon"], budget=config["budget"])
    dataset = load_dataset(CACHE)
    counts = Counter()
    changed = set()
    for n in config["rows"]:
        row = dataset[n-1]
        record = json.loads((folder / f"rep-1/pace/row-{n}.json").read_text())
        tools = DynamicBrowser(row["root_url"], None, n, folder).tools()
        def builder(settings):
            return Builder(instructions(tools, settings.glimpse_limit), question_prompt(row["root_url"], row["question"]),
                           None, settings, Utf8Counter())
        alt = replace(cfg, pressure_power=2) if args.variant == "quadratic" else replace(cfg, pressure_mode="occupancy")
        standard, alternative = builder(cfg), builder(alt)
        previous = standard.previous_tokens
        for step in record["steps"]:
            old_pressure = cfg.pressure(step["step"], previous)
            new_pressure = alt.pressure(step["step"], previous)
            previous = step["input_tokens_actual"]
            if abs(old_pressure - step["pressure"]) > 1e-10:
                raise ValueError("historical pressure mismatch")
            before, size = fit_step(step, record["history"], standard)
            if before != [c["shown"] for c in step["chunks"]] or size != step["input_tokens_estimate"]:
                raise ValueError(f"baseline replay mismatch at row {n}, step {step['step']}")
            if step["input_tokens_actual"] > cfg.budget:
                continue
            after, new_size = fit_step(step, record["history"], alternative, new_pressure)
            if new_pressure < old_pressure:
                counts["lower_pressure_steps"] += 1
            counts["steps"] += 1
            counts["old_size"] += size
            counts["new_size"] += new_size
            if before != after:
                changed.add(n)
                counts["changed_steps"] += 1
                for old, new in zip(before, after):
                    if old != new:
                        counts[f"{old}->{new}"] += 1
    print(json.dumps(dict(counts=counts, changed_rows=sorted(changed)), indent=2))


if __name__ == "__main__":
    main()

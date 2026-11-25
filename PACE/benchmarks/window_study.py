"""Legacy 窗口消融入口。新版固定 20 题使用 benchmarks.evidence_v2。"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .actor_budget import PROTOCOL
from .grading import LEGACY
from .paper_pilot import DenseEncoder, ENCODER
from .research20 import cohort
from .research_browser import ResearchBrowser, browser_settings
from .webwalker_frozen20 import run_cohort
from .webwalkerqa import CACHE, CHAT, DATA_SHA, REVISION, ROOT, load_dataset

OUT = ROOT / "results/webwalker-window-study"
GROUPS = {
    "react": ("react", "max", None),
    "pace": ("pace", "max", None),
    "dag-pace": ("dag-pace", "max", None),
    "pace-window": ("pace", "window", None),
    "dag-pace-window": ("dag-pace", "window", None),
    "pace-delayed": ("pace", "window", 0.8),
    "dag-pace-delayed": ("dag-pace", "window", 0.8),
}


def study_rows(dataset, replacements=None):
    rows = cohort(dataset)
    if not replacements:
        return rows
    removed, added = zip(*replacements)
    if len(set(removed)) != len(removed) or len(set(added)) != len(added):
        raise ValueError("a row may appear only once in the replacements")
    keys = ("type", "lang", "difficulty_level")
    for old, new in replacements:
        if old not in rows or new in rows or not 1 <= new <= len(dataset):
            raise ValueError("replacement must exchange a cohort row for a new dataset row")
        if any(dataset[old - 1]["info"][k] != dataset[new - 1]["info"][k] for k in keys):
            raise ValueError("replacement must match source type, language and difficulty")
    return sorted((set(rows) - set(removed)) | set(added))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--budget", type=int, default=6000, metavar="TOKENS",
                        help="每步动作模型可见输入的 token 预算（默认 6000）")
    parser.add_argument("--groups", nargs="+", choices=GROUPS, default=list(GROUPS))
    parser.add_argument("--replace-row", nargs=2, type=int, action="append", metavar=("OLD", "NEW"),
                        help="按题型、语言和难度匹配换题。可重复使用，更换题单时另用新目录")
    parser.add_argument("--rows", nargs="+", type=int)
    parser.add_argument("--jobs", type=int, default=4, help="每组同时跑的题数")
    parser.add_argument("--parallel-groups", type=int, default=3)
    args = parser.parse_args()
    if args.budget < 1:
        parser.error("--budget must be a positive integer")
    dataset = load_dataset(CACHE)
    try:
        rows = study_rows(dataset, args.replace_row)
    except ValueError as exc:
        parser.error(str(exc))
    if args.jobs < 1 or args.parallel_groups < 1 or len(set(args.groups)) != len(args.groups):
        parser.error("invalid concurrency or duplicate groups")
    if args.rows and (set(args.rows) - set(rows) or len(set(args.rows)) != len(args.rows)):
        parser.error("choose distinct rows from the fixed cohort")
    from dag_pace.strategy import DependencyStrategy

    config = dict(dataset=REVISION, sha256=DATA_SHA, rows=rows, model=CHAT, summary_model=CHAT,
                  encoder=ENCODER, temperature=0, max_steps=24, horizon=16, budget=args.budget,
                  provider_input_budget=80000, workload="window-study-v1", grading_version=LEGACY,
                  token_counter="labhuan-visible-v1", actor_budget_protocol=PROTOCOL, **browser_settings())
    if args.replace_row:
        if len(args.replace_row) == 1:
            config["row_replacement"], = args.replace_row
        else:
            config["row_replacements"] = sorted(args.replace_row)
    encoder = DenseEncoder() if any(GROUPS[g][0] != "react" for g in args.groups) else None

    def run_group(group):
        arm, mode, ratio = GROUPS[group]
        folder = args.out / group
        folder.mkdir(parents=True, exist_ok=True)
        settings = dict(config, arms=[arm], pressure_mode=mode, compression_start_ratio=ratio)

        def browser(root, api, n):
            return ResearchBrowser(root, api, n, folder)

        run_cohort(dataset, settings, folder, args.jobs, browser, encoder=encoder if arm != "react" else None,
                   strategy_factory=DependencyStrategy if arm == "dag-pace" else None, selected_rows=args.rows)

    with ThreadPoolExecutor(args.parallel_groups) as executor:
        futures = {executor.submit(run_group, group): group for group in args.groups}
        incomplete = []
        for future in as_completed(futures):
            try:
                future.result()
            except SystemExit as exc:
                label = futures[future]
                print(f"{label}: {exc}", flush=True)
                incomplete.append(label)
        if incomplete:
            raise SystemExit("resume incomplete groups: " + ", ".join(incomplete))


if __name__ == "__main__":
    main()

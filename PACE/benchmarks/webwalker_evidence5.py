"""从 ReAct 原提交答案前的同一状态回放，对比有无补充原文。"""
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from pace.agent import Tool, run
from pace.memory import Turn
from pace.policy import Settings
from pace.providers import Utf8Counter
from pace.records import write_result
from .grading import LEGACY
from .paper_pilot import FullHistory
from .webwalker_full import FullRunAPI
from .webwalkerqa import CACHE, CHAT, ROOT, benchmark_chat, grade, load_dataset
from .you_public import PublicBrowser

ARCHIVE = ROOT / "results/webwalker-tools20-you-public"
OUT = ROOT / "results/webwalker-evidence5"
DOCUMENTS = Path(__file__).with_name("evidence5.json")


def replay(n, row, documents, arm):
    path = OUT / arm / f"row-{n}.json"
    if path.exists():
        result = json.loads(path.read_text())
        if "grade" in result:
            return
    else:
        old = json.loads((ARCHIVE / f"rep-1/react/row-{n}.json").read_text())
        assert old["question"] == row["question"] and old["steps"][-1]["action"]["tool"] == "finish"
        memory = FullHistory()
        history = old["history"]
        last_visit = max(i for i, t in enumerate(history) if t["kind"] == "visit")
        for i, t in enumerate(history):
            turn = Turn(**t)
            if i == last_visit and arm == "evidence":
                turn = Turn(turn.thought, turn.action, turn.observation + "\nSupplementary source excerpts:\n"
                            + json.dumps(documents, ensure_ascii=False), turn.kind)
            memory.append(turn)
        # 保留原工具说明。后续调用只回放已保存的结果，避免网页在两臂间变化。
        def frozen(name, args):
            for c in reversed(memory.chunks[:len(history)]):
                if json.loads(c.turn.action) == {"tool": name, "args": args}:
                    return c.turn.observation
            return "No additional results available from this snapshot."
        api = FullRunAPI.configured()
        api.job, api.output = [n, arm], OUT
        tools = {k: Tool(v.description, lambda args, k=k: frozen(k, args))
                 for k, v in PublicBrowser(api, (None, None)).tools().items()}
        prompt = (f"Website: {row['root_url']}\nQuestion: {row['question']}\n"
                  "Use search and visit to check the website before answering. If the pages lack "
                  "the requested information, state what is missing.")
        result = run(prompt, tools, lambda messages: benchmark_chat(api, CHAT, messages, "actor"),
                     memory, Settings(16, budget=128000, recent=25, glimpse_limit=0),
                     Utf8Counter(), 24-len(history), lambda: api.last_input_tokens.get("actor"))
        if arm == "control":
            assert result["steps"][0]["input_tokens_estimate"] == old["steps"][-1]["input_tokens_estimate"]
        result.update(row=n, arm=arm, old_answer=old["answer"], old_grade=old["grade"], usage=api.usage,
                      history=[asdict(c.turn) for c in memory.chunks])
        write_result(path, result)
    judge = FullRunAPI.configured()
    judge.job, judge.output = [n, arm], OUT
    result["grade"] = grade(row, result["answer"], judge, CHAT, LEGACY)
    result["usage"].update(judge.usage)
    write_result(path, result)
    print(n, arm, result["grade"]["correct"], len(result["steps"]), flush=True)


def main():
    rows = load_dataset(CACHE)
    cases = json.loads(DOCUMENTS.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(4) as pool:
        futures = [pool.submit(replay, int(n), rows[int(n)-1], excerpts, arm)
                   for n, excerpts in cases.items() for arm in ("control", "evidence")]
        for task in futures:
            task.result()


if __name__ == "__main__":
    main()

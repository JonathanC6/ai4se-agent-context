"""从旧版 ReAct 全文轨迹校准 Labhuan 输入估算，并用不同题号留出验证。"""
import json
from pathlib import Path
from statistics import mean, median

from pace.agent import instructions
from pace.memory import Turn
from pace.providers import Utf8Counter
from pace.providers.encoding import LabhuanCounter, load_count_tokenizer
from .paper_pilot import ASSETS, question_prompt
from .webwalker_live import Browser, LEGACY_BROWSER
from .webwalkerqa import CACHE, ROOT, load_dataset


def prompts(row, record):
    tools = Browser(row["root_url"], None, {row["root_url"]}, LEGACY_BROWSER).tools()
    system = instructions(tools, 0)
    blocks = [question_prompt(row["root_url"], row["question"])]
    for step in record["steps"]:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(blocks)}]
        if Utf8Counter().messages(messages) != step["input_tokens_estimate"]:
            raise ValueError(f"historical prompt mismatch: row {record['row']}, step {step['step']}")
        yield messages, step["input_tokens_actual"]
        i = step["step"]
        if i <= len(record["history"]):
            turn = Turn(**record["history"][i-1])
            blocks.append(f"[C{i} {turn.kind} full]\n" + turn.text())


def main():
    fixed = json.loads(Path(__file__).with_name("webwalker_tools20.json").read_text())["selected"]
    excluded = set(fixed["single_source"] + fixed["multi_source"])
    rows = load_dataset(CACHE)
    codec = load_count_tokenizer(ASSETS / "tokenizer.json")
    training, verification = [], {}
    training_ids = set()
    for path in sorted((ROOT / "results/webwalkerqa-full/rep-1/react").glob("row-*.json")):
        record = json.loads(path.read_text())
        n = record["row"]
        if n in excluded:
            continue
        samples = prompts(rows[n-1], record)
        if n % 3 == 0:
            verification[n] = list(samples)
        else:
            training_ids.add(n)
            for messages, actual in samples:
                tokens = sum(len(codec.encode(m["content"], add_special_tokens=False).ids) for m in messages)
                training.append((tokens, actual))
    if not training or not verification:
        raise ValueError("requires historical full-live-v1 ReAct trajectories")
    # 短提示估网关固定开销，长提示估分词比例；中位数降低网关离群值影响。
    framing = round(median(actual - tokens for tokens, actual in training if tokens < 400))
    scale = round(median((actual - framing) / tokens for tokens, actual in training if tokens > 800), 3)
    raw_errors, calibrated_errors = [], []
    for samples in verification.values():
        counter = LabhuanCounter(codec, scale=scale, framing=framing)
        for messages, actual in samples:
            raw_errors.append(abs(Utf8Counter().messages(messages) - actual))
            calibrated_errors.append(abs(counter.messages(messages) - actual))
            counter.observe(messages, actual)
    print(json.dumps(dict(training_questions=len(training_ids), training_steps=len(training),
                          heldout_questions=len(verification), heldout_steps=len(raw_errors),
                          framing=framing, scale=scale, utf8_mae=mean(raw_errors),
                          calibrated_mae=mean(calibrated_errors), calibrated_median=median(calibrated_errors))))


if __name__ == "__main__":
    main()

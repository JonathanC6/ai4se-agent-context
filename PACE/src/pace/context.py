"""Build one decision context in chronological order and enforce the model input budget."""
from dataclasses import dataclass
from typing import List, Optional

from .memory import Chunk, Memory
from .policy import Level, Settings, relative_weights, unit

try:
    import numpy as np
except ImportError:  # The offline smoke test also works with the standard library.
    np = None

class BudgetExceeded(ValueError):
    pass


def block_text(chunk, level, body):
    label = f"[C{chunk.id} {chunk.turn.kind} {level.name.lower()}]"
    return label + "\n" + body if body else label


@dataclass
class Selection:
    chunk: Chunk
    representations: dict
    requested: Level
    shown: Level
    cosine: Optional[float]
    weight: Optional[float]
    summary_state: str

    def block(self, level):
        return block_text(self.chunk, level, self.representations[level])


@dataclass
class Context:
    messages: list
    tokens: int
    step: int
    pressure: float
    boundaries: tuple
    selections: List[Selection]

    adjustment: Optional[dict] = None
    window: Optional[dict] = None

    def trace(self):
        return {**({"adjustment": self.adjustment} if self.adjustment is not None else {}),
                **({"window": self.window} if self.window is not None else {}),
                "step": self.step, "input_tokens_estimate": self.tokens, "pressure": self.pressure,
                "thresholds": self.boundaries, "chunks": [
                    {"id": s.chunk.id, "cos": s.cosine, "weight": s.weight,
                     "selected": s.requested.name, "shown": s.shown.name,
                     "summaries": s.summary_state} for s in self.selections]}


class Builder:
    def __init__(self, system, query, memory: Memory, settings: Settings, counter, strategy=None,
                 trace_window=False):
        self.strategy = strategy
        self.system, self.query = system, query
        self.memory, self.settings, self.counter = memory, settings, counter
        self.previous_tokens = counter.messages(self.messages([]))
        self.trace_window = trace_window or settings.pressure_mode == "window" or settings.compression_start_ratio is not None
        self.previous_blocks = {}
        self.activation_step = None
        self.first_organization_step = None
        self.last_window = None

    def messages(self, selections):
        return self.messages_from_blocks([s.block(s.shown) for s in selections])

    def messages_from_blocks(self, blocks):
        return [{"role": "system", "content": self.system},
                {"role": "user", "content": "\n\n".join([self.query, *blocks])}]

    def measure_window(self, chunks, old_count, step):
        full = [block_text(c, Level.FULL, c.full) for c in chunks]
        full_tokens = self.counter.messages(self.messages_from_blocks(full))
        # 当前候选保留上次实际送出的粒度。新块、最近块和新设锚点按全文计入。
        current = list(full)
        anchors = getattr(self.strategy, "anchors", ())
        for i, chunk in enumerate(chunks[:old_count]):
            if chunk.id not in anchors and chunk.id in self.previous_blocks:
                current[i] = self.previous_blocks[chunk.id]
        current_tokens = full_tokens if current == full else self.counter.messages(self.messages_from_blocks(current))

        ratio = self.settings.compression_start_ratio
        phase = "multilevel" if old_count else "full_history"
        if ratio is not None:
            if self.activation_step is None and full_tokens >= self.settings.budget * ratio:
                self.activation_step = step
            if self.activation_step is None:
                phase = "full_history"
            elif not old_count:
                phase = "awaiting_old_chunk"
            else:
                if self.first_organization_step is None:
                    self.first_organization_step = step
                if step == self.first_organization_step:
                    phase = "first_multilevel"
        return dict(full_input_estimate=full_tokens, current_input_estimate=current_tokens,
                    compression_start_ratio=ratio, activation_step=self.activation_step,
                    first_organization_step=self.first_organization_step, phase=phase)

    def build(self):
        chunks = self.memory.chunks
        step = len(chunks) + 1
        # 步数按完整轨迹累计；改进策略可在评分前排除失活块。
        if self.strategy:
            chunks = [c for c in chunks if self.strategy.active(c.id)]
        old, recent = chunks[:-self.settings.recent], chunks[-self.settings.recent:]
        if self.trace_window:
            self.last_window = self.measure_window(chunks, len(old), step)
        ratio = self.settings.compression_start_ratio
        pressure_tokens = (self.last_window["current_input_estimate"] if self.settings.pressure_mode == "window"
                           else self.previous_tokens)
        if ratio is not None and self.last_window["phase"] != "multilevel":
            # 触发当步采用基础阈值；之后即使窗口回落也继续分档。
            pressure = 0.0
        else:
            pressure = self.settings.pressure(step, pressure_tokens)
        if ratio is not None and self.activation_step is None:
            old = []  # 门槛前所有活跃块均展示全文，入库摘要照常生成。
        bounds = self.settings.boundaries(pressure)
        scores = []
        if old:
            query = "\n\n".join([self.query] + [c.full for c in recent])
            q = unit(self.memory.encode(query))
            if len(q) != len(old[0].key):
                raise ValueError("query and historical keys have different dimensions")
            if np is None:
                scores = [sum(a * b for a, b in zip(q, c.key)) for c in old]
            else:
                scores = (np.asarray([c.key for c in old]) @ q).tolist()
        # 原始 PACE 仅根据语义权重和上下文压力选择四档粒度。
        weights = relative_weights(scores, self.settings.temperature)
        rows = []
        for i, chunk in enumerate(chunks):
            score, weight = (scores[i], weights[i]) if i < len(old) else (None, None)
            desired = self.settings.level(weight, bounds) if weight is not None else Level.FULL
            versions = {Level.PLACEHOLDER: "", Level.FULL: chunk.full}
            summary, state = chunk.summary_snapshot()
            if summary is not None and self.settings.multi_level:
                versions.update({Level.BRIEF: summary.brief, Level.DETAILED: summary.detailed})
            shown = desired if desired in versions else Level.FULL
            rows.append(Selection(chunk, versions, desired, shown, score, weight, state))
        organize = ratio is None or self.activation_step is not None
        adjustment = self.strategy.adjust(rows, len(old)) if self.strategy and organize else None
        messages, tokens = self.fit(rows, len(old))
        self.previous_tokens = tokens
        if self.trace_window:
            self.previous_blocks = {s.chunk.id: s.block(s.shown) for s in rows if s.shown != Level.FULL}
            self.last_window["organized_input_estimate"] = tokens
        return Context(messages, tokens, step, pressure, bounds, rows, adjustment, self.last_window)

    def fit(self, rows, old_count):
        messages = self.messages(rows)
        used = self.counter.messages(messages)
        if used <= self.settings.budget:
            return messages, used
        # The paper leaves the overflow tie-break unspecified. Demote least relevant first.
        # Estimate savings on individual blocks, verify the entire chat after each batch.
        candidates = rows[:old_count]
        if self.strategy:
            candidates = self.strategy.demotable(candidates)
        else:
            candidates = sorted(candidates, key=lambda r: (r.weight, r.chunk.id))
        for row in candidates:
            current = self.counter.text(row.block(row.shown))
            for level in sorted(row.representations, reverse=True):
                if level >= row.shown:
                    continue
                cost = self.counter.text(row.block(level))
                if cost >= current and level != Level.PLACEHOLDER:
                    continue
                row.shown = level
                used -= current - cost
                current = cost
                if used <= self.settings.budget:
                    messages = self.messages(rows)
                    used = self.counter.messages(messages)
                    if used <= self.settings.budget:
                        return messages, used
        messages = self.messages(rows)
        used = self.counter.messages(messages)
        if used > self.settings.budget:
            raise BudgetExceeded(f"required context (system, query, recent turns and any protected anchors) need {used} tokens "
                                 f"(budget {self.settings.budget})")
        return messages, used

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
        label = f"[C{self.chunk.id} {self.chunk.turn.kind} {level.name.lower()}]"
        text = self.representations[level]
        return label + "\n" + text if text else label


@dataclass
class Context:
    messages: list
    tokens: int
    step: int
    pressure: float
    boundaries: tuple
    selections: List[Selection]

    adjustment: Optional[dict] = None

    def trace(self):
        return {**({"adjustment": self.adjustment} if self.adjustment is not None else {}), "step": self.step, "input_tokens_estimate": self.tokens, "pressure": self.pressure,
                "thresholds": self.boundaries, "chunks": [
                    {"id": s.chunk.id, "cos": s.cosine, "weight": s.weight,
                     "selected": s.requested.name, "shown": s.shown.name,
                     "summaries": s.summary_state} for s in self.selections]}


class Builder:
    def __init__(self, system, query, memory: Memory, settings: Settings, counter, strategy=None):
        self.strategy = strategy
        self.system, self.query = system, query
        self.memory, self.settings, self.counter = memory, settings, counter
        self.previous_tokens = counter.messages(self.messages([]))

    def messages(self, selections):
        blocks = [self.query] + [s.block(s.shown) for s in selections]
        return [{"role": "system", "content": self.system},
                {"role": "user", "content": "\n\n".join(blocks)}]

    def build(self):
        chunks = self.memory.chunks
        step = len(chunks) + 1
        # 步数按完整轨迹累计；改进策略可在评分前排除失活块。
        if self.strategy:
            chunks = [c for c in chunks if self.strategy.active(c.id)]
        pressure = self.settings.pressure(step, self.previous_tokens)
        bounds = self.settings.boundaries(pressure)
        old, recent = chunks[:-self.settings.recent], chunks[-self.settings.recent:]
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
        adjustment = self.strategy.adjust(rows, len(old)) if self.strategy else None
        messages, tokens = self.fit(rows, len(old))
        self.previous_tokens = tokens
        return Context(messages, tokens, step, pressure, bounds, rows, adjustment)

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

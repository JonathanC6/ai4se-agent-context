"""Append-only external memory: raw interactions, cached keys and asynchronous summaries."""
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from .policy import unit


@dataclass(frozen=True)
class Turn:
    thought: str
    action: str
    observation: str
    kind: str = "tool"

    def text(self):
        return f"Thought: {self.thought}\nAction: {self.action}\nObservation: {self.observation}"


@dataclass(frozen=True)
class Summaries:
    detailed: str
    brief: str

    def __post_init__(self):
        if not all(isinstance(x, str) and x.strip() for x in (self.detailed, self.brief)):
            raise ValueError("both summary levels must contain text")


@dataclass(frozen=True)
class Chunk:
    id: int
    turn: Turn
    full: str
    key: Tuple[float, ...]
    summaries: Future

    def summary_snapshot(self) -> Tuple[Optional[Summaries], str]:
        if not self.summaries.done():
            return None, "pending"
        try:
            return self.summaries.result(), "ready"
        except Exception as exc:
            return None, "failed/" + type(exc).__name__


class Memory:
    """One writer (the agent loop). Background workers never modify a stored turn."""
    def __init__(self, encode: Callable[[str], Sequence[float]],
                 summarize: Callable[[str], Summaries], workers=2):
        self.encode = encode
        self.summarize = summarize
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pace-summary")
        self.chunks: List[Chunk] = []

    def append(self, turn: Turn):
        full = turn.text()
        # 全文的键只算一次，摘要在后台生成。
        key = unit(self.encode(full))
        if self.chunks and len(key) != len(self.chunks[0].key):
            raise ValueError("embedding dimensions changed during the episode")
        chunk = Chunk(len(self.chunks) + 1, turn, full, key, self.pool.submit(self.summarize, full))
        self.chunks.append(chunk)
        return chunk

    def glimpse(self, ids, limit=3):
        if (not isinstance(ids, list) or not 1 <= len(ids) <= limit
                or any(type(i) is not int or not 1 <= i <= len(self.chunks) for i in ids)
                or len(set(ids)) != len(ids)):
            raise ValueError(f"provide 1 to {limit} distinct historical chunk IDs")
        return "\n\n".join(f"[C{i}]\n{self.chunks[i-1].full}" for i in ids)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.pool.shutdown(wait=True)

"""先用原四级预算器；只有普通降档仍超限，才缩短最近观察。"""
import json
import re
from concurrent.futures import Future

from pace.context import BudgetExceeded, Builder
from pace.memory import Chunk, Memory
from pace.policy import Level, unit
from .browser import terms


class PreparedMemory(Memory):
    def __init__(self, encoder):
        self.encode=encoder
        self.chunks=[]

    def store(self, turn, summary):
        future=Future()
        future.set_result(summary)
        full=turn.text()
        chunk=Chunk(len(self.chunks)+1,turn,full,unit(self.encode(full)),future)
        self.chunks.append(chunk)
        return chunk


def compact(turn, query, limit):
    """只改变展示。保留题目相关的原文片段和数值，整块仍可用编号恢复。"""
    raw=turn.observation.replace('\\n','\n').replace('\\"','"')
    pieces=[p.strip() for p in re.split(r'\n|(?<=[。；;])|(?<=[.!?])\s+',raw) if p.strip()]
    spans=[p[i:i+320] for p in pieces for i in range(0,len(p),320)]
    keys=terms(query)
    def score(i):
        seg=spans[i]
        return (len(keys & terms(seg)), bool(re.search(r'\d',seg)), -i)
    chosen=sorted(range(len(spans)),key=score,reverse=True)[:max(1,limit//240)]
    return "Selected excerpts; full observation available via glimpse.\n"+"\n".join(spans[i] for i in sorted(chosen))[:limit]


class EvidenceBuilder(Builder):
    def __init__(self,system,query,memory,settings,counter,book,strategy=None):
        self.book=book
        self.question_prompt=query
        super().__init__(system,query,memory,settings,counter,strategy,trace_window=True)

    def build(self):
        state=[]
        for sid,need in self.book.needs.items():
            facts=[f for f in self.book.active_facts() if f.slot==sid]
            refs=[dict(value=f.value,quote=f.quote[:180],chunk=f.chunk,source=f.source[:120]) for f in facts[:2]]
            state.append(dict(id=sid,need=need,evidence=refs))
        self.query=self.question_prompt+"\nEvidence checklist (observed data): "+json.dumps(state,ensure_ascii=False)
        return super().build()

    def fit(self,rows,old_count):
        try:
            return super().fit(rows,old_count)
        except BudgetExceeded:
            if not rows:
                raise
        shortened={}
        for limit in (1200,480,140):
            for row in rows[old_count:]:
                if self.strategy and row.chunk.id in self.strategy.anchors:
                    continue
                text=compact(row.chunk.turn,self.question_prompt,limit)
                if self.counter.text(text)>=self.counter.text(row.representations[row.shown]):
                    continue
                row.representations[Level.BRIEF]=text
                row.shown=Level.BRIEF
                shortened[row.chunk.id]=limit
                msgs=self.messages(rows)
                used=self.counter.messages(msgs)
                if used<=self.settings.budget:
                    self.last_window["recent_excerpt_chars"]=shortened
                    return msgs,used
        raise BudgetExceeded(f"compact evidence context still needs {self.counter.messages(self.messages(rows))} tokens")

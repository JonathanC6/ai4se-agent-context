"""在 PACE 四档表示上叠加依赖、锚点和版本替代。"""
from pace.policy import Level


class DependencyStrategy:
    instructions = (
        "Alongside tool, args and note, emit integer arrays used_chunk_ids (visible IDs "
        "actually used to choose this action), critical_anchor_ids (durable, indispensable "
        "evidence to retain verbatim), release_anchor_ids (anchors no longer essential) "
        "and supersedes_chunk_ids (older results wholly corrected by the most recent "
        "observed chunk). Use [] when none. Differences between sources alone do not "
        "establish a correction. Never cite a future result."
    )

    def __init__(self, top_k=2, anchors=True, supersedes=True):
        self.use_anchors = anchors
        self.use_supersedes = supersedes
        if not supersedes:
            self.instructions = ("Alongside tool, args and note, emit integer array used_chunk_ids "
                                 "(visible IDs actually used to choose this action). Use [] when none.")
            if anchors:
                self.instructions += (" Also emit critical_anchor_ids (durable, indispensable evidence "
                                      "to retain verbatim) and release_anchor_ids (anchors no longer essential).")
            self.instructions += " Never cite a future result."
        self.top_k = top_k
        self.parents = {}
        self.anchors = set()
        self.replacements = {}
        self.failed = set()
        self.promoted = set()

    def active(self, chunk_id):
        return chunk_id not in self.replacements

    def resolve(self, chunk_id):
        # 替代边只指向更晚的块，版本链一定有终点。
        while chunk_id in self.replacements:
            chunk_id = self.replacements[chunk_id]
        return chunk_id

    def record(self, new_id, reply, visible, failed=False):
        def accepted(field):
            values = reply.get(field, [])
            if not isinstance(values, list):
                return set()
            return {i for i in values if type(i) is int and i in visible and 0 < i < new_id}

        used = accepted("used_chunk_ids")
        latest = new_id - 1
        parents = set(used)
        if latest in visible:
            parents.add(latest)
        self.parents[new_id] = parents
        if failed:
            self.failed.add(new_id)
        # 作答时只见过上一条观察，所以只能用它声明旧版本失活。
        replaced = set()
        if self.use_supersedes and latest in visible and latest not in self.failed:
            replaced = {i for i in accepted("supersedes_chunk_ids") if i < latest}
            self.replacements.update({i: latest for i in replaced})
        if self.use_anchors:
            self.anchors.update(accepted("critical_anchor_ids"))
        self.anchors.difference_update(replaced | accepted("release_anchor_ids"))
        return {"parents": sorted(parents), "used": sorted(used), "anchors": sorted(self.anchors),
                "replaced": sorted(replaced), "replacement": latest if replaced else None}

    def adjust(self, rows, old_count):
        # 最近两块已是全文；在参与余弦评分的旧块中选种子。
        ranked = sorted(rows[:old_count], key=lambda r: (-r.weight, r.chunk.id))
        seeds = [r.chunk.id for r in ranked[:self.top_k]]
        frontier = set(seeds)
        ancestors = set()
        for _ in range(2):
            frontier = {self.resolve(parent) for node in frontier
                        for parent in self.parents.get(node, ())}
            ancestors.update(frontier)
        self.promoted = set()
        changes = {}
        for row in rows[:old_count]:
            i = row.chunk.id
            base = row.requested
            if i in self.anchors:
                target = Level.FULL
            elif i in ancestors:
                target = Level(min(Level.FULL, base + 1))
            else:
                continue
            if base != target:
                self.promoted.add(i)
                changes[i] = [base.name, target.name]
            row.requested = target
            row.shown = target if target in row.representations else Level.FULL
        return {"seeds": seeds, "ancestors": sorted(ancestors), "anchors": sorted(self.anchors),
                "inactive": sorted(self.replacements), "upgrades": changes}

    def demotable(self, rows):
        # 先压缩普通历史，再压缩依赖。锚点放不下时由共用预算器显式报错。
        return sorted((r for r in rows if r.chunk.id not in self.anchors),
                      key=lambda r: (r.chunk.id in self.promoted, r.weight, r.chunk.id))

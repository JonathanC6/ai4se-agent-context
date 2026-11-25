"""PACE equations (5)–(7). Input vectors are L2-normalized once at encoding."""
import math
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, Sequence, Tuple


class Level(IntEnum):
    PLACEHOLDER = 0
    BRIEF = 1
    DETAILED = 2
    FULL = 3


@dataclass(frozen=True)
class Settings:
    horizon: int
    budget: int = 128_000
    recent: int = 2
    temperature: float = 0.3
    thresholds: Tuple[float, float, float] = (0.4, 0.8, 1.5)
    adaptation: float = 0.5
    multi_level: bool = True
    glimpse_limit: int = 3
    guided_glimpse: bool = False
    pressure_power: float = 1.0
    pressure_mode: str = "max"
    compression_start_ratio: Optional[float] = None

    def __post_init__(self):
        if min(self.horizon, self.budget, self.recent) < 1:
            raise ValueError("horizon, budget and recent must be positive")
        a, b, g = self.thresholds
        if not (0 <= a < b < g and all(math.isfinite(x) for x in self.thresholds)):
            raise ValueError("expected finite thresholds: 0 <= alpha < beta < gamma")
        if not (math.isfinite(self.temperature) and self.temperature > 0
                and math.isfinite(self.adaptation) and self.adaptation >= 0):
            raise ValueError("invalid temperature or adaptation")
        if not 0 <= self.glimpse_limit <= 3:
            raise ValueError("glimpse_limit must be between 0 and 3")
        if not math.isfinite(self.pressure_power) or self.pressure_power <= 0:
            raise ValueError("pressure_power must be finite and positive")
        if self.pressure_mode not in ("max", "occupancy", "window"):
            raise ValueError("unknown pressure mode")
        if self.compression_start_ratio is not None and not 0 < self.compression_start_ratio <= 1:
            raise ValueError("compression_start_ratio must be in (0, 1]")

    def pressure(self, step: int, previous_tokens: int) -> float:
        """保留旧参数名。window 传本轮分档前的估值，其他模式传上步输入。"""
        occupancy = min(1.0, previous_tokens / self.budget)
        if self.pressure_mode == "window":
            return occupancy
        progress = min(1.0, step / self.horizon)
        if self.pressure_mode == "occupancy":
            # 窗口越空，进度超过占用率的那一部分就越少计入压力。
            return occupancy + occupancy * max(0.0, progress - occupancy)
        return max(progress, occupancy)

    def boundaries(self, pressure):
        # 原论文用线性压力。平方曲线在中低压力时保留更多细节，两端阈值一致。
        scale = 1 + self.adaptation * pressure ** self.pressure_power
        return tuple(x * scale for x in self.thresholds)

    def level(self, weight, boundaries):
        if self.multi_level:
            return Level(sum(weight > x for x in boundaries))
        return Level.FULL if weight > boundaries[-1] else Level.PLACEHOLDER


def p95(lengths):
    if not lengths or any(type(n) is not int or n <= 0 for n in lengths):
        raise ValueError("validation lengths must be a nonempty list of positive integers")
    return sorted(lengths)[math.ceil(0.95 * len(lengths)) - 1]


def unit(vector):
    values = tuple(float(x) for x in vector)
    norm = math.sqrt(sum(x * x for x in values))
    if not norm or not math.isfinite(norm):
        raise ValueError("encoder returned a zero or nonfinite vector")
    return tuple(x / norm for x in values)


def relative_weights(scores: Sequence[float], temperature: float):
    if not scores:
        return []
    peak = max(scores)
    exps = [math.exp((s - peak) / temperature) for s in scores]
    scale = len(exps) / sum(exps)
    return [e * scale for e in exps]

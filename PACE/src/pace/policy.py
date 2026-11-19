"""PACE equations (5)–(7). Input vectors are L2-normalized once at encoding."""
import math
from dataclasses import dataclass
from enum import IntEnum
from typing import Sequence, Tuple


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

    def pressure(self, step: int, previous_tokens: int) -> float:
        return min(1.0, max(step / self.horizon, previous_tokens / self.budget))

    def boundaries(self, pressure):
        return tuple(x * (1 + self.adaptation * pressure) for x in self.thresholds)

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

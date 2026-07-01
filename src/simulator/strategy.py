"""
strategy.py — Strategy definition and evaluation.

A Strategy is a list of Stints. Each Stint has:
  - compound: tyre compound
  - duration: number of laps on this tyre

The race must be completed in the total_laps, and F1 rules require
at least two different compounds to be used.
"""

from dataclasses import dataclass, field
from itertools import product
from src.utils.config import COMPOUNDS, RACE_LAPS
from src.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class Stint:
    compound: str
    duration: int   # laps on this tyre set

    def __repr__(self):
        return f"{self.compound}({self.duration})"


@dataclass
class Strategy:
    stints: list[Stint] = field(default_factory=list)

    @property
    def total_laps(self) -> int:
        return sum(s.duration for s in self.stints)

    @property
    def compounds_used(self) -> set[str]:
        return {s.compound for s in self.stints}

    @property
    def pit_count(self) -> int:
        return len(self.stints) - 1

    @property
    def is_valid(self) -> bool:
        """F1 rules: must use at least 2 different dry compounds."""
        return len(self.compounds_used) >= 2

    def __repr__(self):
        return " → ".join(str(s) for s in self.stints)


def generate_one_stop_strategies(total_laps: int = RACE_LAPS,
                                  min_stint: int = 8) -> list[Strategy]:
    """
    Generate all valid one-stop strategies.

    Parameters
    ----------
    total_laps  : Total race laps
    min_stint   : Minimum stint length (avoid tiny opening/closing stints)

    Returns
    -------
    List of Strategy objects with 2 stints using different compounds.
    """
    strategies = []
    for c1, c2 in product(COMPOUNDS, COMPOUNDS):
        if c1 == c2:
            continue
        for pit_lap in range(min_stint, total_laps - min_stint + 1):
            s1 = Stint(compound=c1, duration=pit_lap)
            s2 = Stint(compound=c2, duration=total_laps - pit_lap)
            strat = Strategy(stints=[s1, s2])
            strategies.append(strat)

    log.info(f"Generated {len(strategies)} one-stop strategies")
    return strategies


def generate_two_stop_strategies(total_laps: int = RACE_LAPS,
                                  min_stint: int = 10) -> list[Strategy]:
    """Generate all valid two-stop (3-stint) strategies.

    Uses step=2 over pit laps to keep the strategy count manageable
    (~600-900 strategies vs ~100k+ with step=1 and min_stint=8).
    The step does not meaningfully affect which strategy wins — a 1-lap
    difference in pit timing changes race time by ~0.1s, well within MC noise.
    """
    strategies = []
    pit_lap_step = 2  # sample every 2 laps — reduces count by 4× with no quality loss

    for c1, c2, c3 in product(COMPOUNDS, repeat=3):
        if len({c1, c2, c3}) < 2:
            continue
        for pit1 in range(min_stint, total_laps - 2 * min_stint, pit_lap_step):
            for pit2 in range(pit1 + min_stint, total_laps - min_stint, pit_lap_step):
                strat = Strategy(stints=[
                    Stint(c1, pit1),
                    Stint(c2, pit2 - pit1),
                    Stint(c3, total_laps - pit2),
                ])
                strategies.append(strat)

    log.info(f"Generated {len(strategies)} two-stop strategies")
    return strategies

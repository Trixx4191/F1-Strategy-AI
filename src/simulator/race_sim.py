"""
race_sim.py — Core deterministic race simulation engine.

Given a Strategy and fitted models, computes total race time.
The Monte Carlo module calls this thousands of times with sampled noise.

Rival-aware mode
────────────────
Pass a RivalState to simulate_race_with_rival() to get lap-by-lap gap
tracking alongside the strategy simulation. This feeds the undercut /
overcut analysis in rival.py.
"""

from __future__ import annotations

import numpy as np
from src.simulator.strategy import Strategy
from src.models.tyre_deg import TyreDegModel
from src.models.pit_loss import get_pit_loss
from src.utils.logger import get_logger

log = get_logger(__name__)


def simulate_race(strategy: Strategy,
                  deg_model: TyreDegModel,
                  pit_loss: float,
                  noise_std: float = 0.0) -> dict:
    """
    Simulate a race with a given strategy and return total time + lap times.

    Parameters
    ----------
    strategy    : Strategy object (list of Stints)
    deg_model   : Fitted TyreDegModel
    pit_loss    : Time lost per pit stop (seconds)
    noise_std   : Lap time noise std dev (0 for deterministic, >0 for MC)

    Returns
    -------
    dict with:
        total_time    : float — total race time in seconds
        lap_times     : list[float] — predicted lap time each lap
        pit_laps      : list[int] — lap numbers where pits happen
        strategy_repr : str
    """
    lap_times = []
    pit_laps = []
    lap_number = 1
    total_time = 0.0

    for i, stint in enumerate(strategy.stints):
        compound = stint.compound

        if compound not in deg_model.models:
            # Fallback if compound not in this race data
            log.debug(f"No model for {compound} — using MEDIUM as proxy")
            compound = "MEDIUM" if "MEDIUM" in deg_model.models else list(deg_model.models.keys())[0]

        for tyre_age in range(1, stint.duration + 1):
            predicted = float(deg_model.predict(compound, tyre_age))

            if noise_std > 0:
                predicted += np.random.normal(0, noise_std)

            lap_times.append(predicted)
            total_time += predicted
            lap_number += 1

        # Add pit stop time loss (except after the last stint)
        if i < len(strategy.stints) - 1:
            pit_laps.append(lap_number - 1)
            total_time += pit_loss

    return {
        "total_time": total_time,
        "lap_times": lap_times,
        "pit_laps": pit_laps,
        "strategy_repr": str(strategy),
        "pit_count": strategy.pit_count,
    }


def compare_strategies(strategies: list[Strategy],
                       deg_model: TyreDegModel,
                       pit_loss: float) -> list[dict]:
    """
    Run deterministic simulation for a list of strategies.
    Returns results sorted by total_time ascending (best first).
    """
    results = []
    for strat in strategies:
        try:
            result = simulate_race(strat, deg_model, pit_loss, noise_std=0.0)
            result["strategy"] = strat
            results.append(result)
        except Exception as e:
            log.debug(f"Strategy {strat} failed: {e}")

    results.sort(key=lambda r: r["total_time"])
    return results


def simulate_race_with_rival(
    our_strategy: Strategy,
    rival_strategy: Strategy,
    deg_model: TyreDegModel,
    pit_loss: float,
    initial_gap: float = 2.0,
    noise_std: float = 0.0,
) -> dict:
    """
    Simulate both our race and a rival's race lap by lap, tracking the
    gap between the two cars on every lap.

    This is the engine that feeds undercut / overcut analysis.

    Parameters
    ----------
    our_strategy    : Our Strategy (list of Stints)
    rival_strategy  : Rival's Strategy
    deg_model       : Fitted TyreDegModel
    pit_loss        : Pit stop time loss in seconds
    initial_gap     : Gap at race start in seconds
                      Positive = rival is ahead. Negative = rival is behind.
    noise_std       : Per-lap Gaussian noise std dev (0 = deterministic)

    Returns
    -------
    dict with:
        our_lap_times       : list[float]
        rival_lap_times     : list[float]
        gap_per_lap         : list[float] — positive = rival ahead each lap
        our_pit_laps        : list[int]
        rival_pit_laps      : list[int]
        final_gap           : float — positive = rival finished ahead
        we_won_position     : bool — True if we finished ahead (gap < 0)
        our_total_time      : float
        rival_total_time    : float
    """
    def _build_lap_sequence(strategy: Strategy) -> tuple[list[float], list[int]]:
        """Return (lap_times_including_pit_loss, pit_laps)."""
        lap_times: list[float] = []
        pit_laps: list[int] = []
        lap_num = 1

        for i, stint in enumerate(strategy.stints):
            compound = stint.compound
            if compound not in deg_model.models:
                compound = list(deg_model.models.keys())[0]

            for tyre_age in range(1, stint.duration + 1):
                t = float(deg_model.predict(compound, tyre_age))
                if noise_std > 0:
                    t += np.random.normal(0, noise_std)
                lap_times.append(t)
                lap_num += 1

            if i < len(strategy.stints) - 1:
                pit_laps.append(lap_num - 1)
                # Pit loss is added to the pit lap's time
                lap_times[-1] += pit_loss

        return lap_times, pit_laps

    our_laps, our_pit_laps = _build_lap_sequence(our_strategy)
    rival_laps, rival_pit_laps = _build_lap_sequence(rival_strategy)

    # Align lap counts (handle different total_laps gracefully)
    n = min(len(our_laps), len(rival_laps))
    our_laps = our_laps[:n]
    rival_laps = rival_laps[:n]

    # Compute cumulative gap per lap
    # gap[i] = initial_gap + sum(rival_lap_times[:i]) - sum(our_lap_times[:i])
    # Positive gap = rival is ahead (they started ahead and this compounds)
    gap_per_lap: list[float] = []
    cumulative_gap = initial_gap

    for i in range(n):
        # Each lap: gap changes by (rival's lap time - our lap time)
        # If rival runs a slower lap, the gap closes (positive → smaller)
        cumulative_gap += rival_laps[i] - our_laps[i]
        gap_per_lap.append(round(cumulative_gap, 4))

    final_gap = gap_per_lap[-1] if gap_per_lap else initial_gap

    return {
        "our_lap_times":    our_laps,
        "rival_lap_times":  rival_laps,
        "gap_per_lap":      gap_per_lap,
        "our_pit_laps":     our_pit_laps,
        "rival_pit_laps":   rival_pit_laps,
        "final_gap":        round(final_gap, 3),
        "we_won_position":  final_gap < 0,   # gap < 0 = rival behind = we beat them
        "our_total_time":   sum(our_laps),
        "rival_total_time": sum(rival_laps),
    }

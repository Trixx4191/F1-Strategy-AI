"""
pit_loss.py — Pit stop time loss estimator.

Pit loss = time lost versus staying out:
  approx (pit lane travel time + stationary time) - (normal lap delta)

In practice this is 18–24 seconds depending on team, track, and traffic.
We estimate from actual race data where available, else use config defaults.
"""

import pandas as pd
import numpy as np
from src.utils.config import PIT_LOSS, TARGET_TEAM
from src.utils.logger import get_logger

log = get_logger(__name__)


def estimate_pit_loss_from_data(pit_stops: pd.DataFrame) -> float:
    """
    Estimate mean pit stop duration from actual race data.

    Parameters
    ----------
    pit_stops : DataFrame with PitDuration column (from loader.get_pit_stops)

    Returns
    -------
    Mean pit stop duration in seconds (float).
    """
    if pit_stops.empty or "PitDuration" not in pit_stops.columns:
        log.warning("No pit stop data available — using config default")
        return PIT_LOSS.get(TARGET_TEAM, PIT_LOSS["DEFAULT"])

    clean = pit_stops["PitDuration"].dropna()
    # Remove obvious errors (< 15s or > 60s suggests data artefact)
    clean = clean[(clean > 15) & (clean < 60)]

    if clean.empty:
        return PIT_LOSS.get(TARGET_TEAM, PIT_LOSS["DEFAULT"])

    mean_pit = clean.mean()
    std_pit = clean.std()
    log.info(f"Pit loss estimated from data: {mean_pit:.2f}s ± {std_pit:.2f}s "
             f"(n={len(clean)})")
    return float(mean_pit)


def get_pit_loss(pit_stops: pd.DataFrame | None = None,
                 team: str = TARGET_TEAM) -> float:
    """
    Get pit stop time loss to use in simulation.

    Priority:
    1. Estimated from actual race data
    2. Team-specific config default
    3. Global default
    """
    if pit_stops is not None:
        return estimate_pit_loss_from_data(pit_stops)

    loss = PIT_LOSS.get(team, PIT_LOSS["DEFAULT"])
    log.info(f"Using config pit loss for {team}: {loss}s")
    return loss

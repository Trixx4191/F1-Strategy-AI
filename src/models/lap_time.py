"""
lap_time.py — Lap time prediction model.

Wraps the tyre degradation model with safety car probability and
fuel load adjustments to produce a full-race lap time distribution.

Why this is separate from tyre_deg.py:
  tyre_deg.py answers: "how fast is this tyre at age N?"
  lap_time.py answers:  "what will lap N of the race actually take?"

The key additions:
  - Safety car probability (from historical rate)
  - Fuel correction (stripped from tyre model, added back race-wide)
  - Track evolution (rubber laid down improves lap times ~0.05s/lap early on)
"""

import numpy as np
import pandas as pd
from src.models.tyre_deg import TyreDegModel
from src.utils.config import RACE_LAPS
from src.utils.logger import get_logger

log = get_logger(__name__)

# Historical safety car probability per lap (F1 average ~0.08 SC events/race,
# ~5 laps duration each => ~0.007 probability any given lap is SC)
SC_PROB_PER_LAP = 0.007
SC_DELTA_SECONDS = 30.0   # approximate time lost per SC lap vs green flag

# Track evolution: early laps are ~0.1s slower, effect decays by lap 20
TRACK_EVOLUTION_PEAK = 0.10   # seconds slower on lap 1 vs lap 20+
TRACK_EVOLUTION_DECAY = 20    # laps to reach full rubber


def track_evolution_delta(lap_number: int) -> float:
    """
    Time penalty due to green (un-rubbered) track surface.
    Decays exponentially — biggest effect on lap 1, negligible by lap 20.
    """
    return TRACK_EVOLUTION_PEAK * np.exp(-lap_number / TRACK_EVOLUTION_DECAY)


def predict_lap_time(
    lap_number: int,
    tyre_age: int,
    compound: str,
    deg_model: TyreDegModel,
    noise_std: float = 0.0,
    apply_track_evolution: bool = True,
) -> float:
    """
    Predict a single lap time given race context.

    Parameters
    ----------
    lap_number            : Lap number in the race (1-indexed)
    tyre_age              : Age of the current tyre set in laps
    compound              : "SOFT", "MEDIUM", or "HARD"
    deg_model             : Fitted TyreDegModel instance
    noise_std             : Gaussian noise std dev (0 = deterministic)
    apply_track_evolution : Whether to add track surface delta

    Returns
    -------
    Predicted lap time in seconds.
    """
    base = float(deg_model.predict(compound, tyre_age))

    if apply_track_evolution:
        base += track_evolution_delta(lap_number)

    if noise_std > 0:
        base += np.random.normal(0, noise_std)

    return base


def predict_race_lap_times(
    strategy_stints: list[tuple[str, int]],   # [(compound, duration), ...]
    deg_model: TyreDegModel,
    noise_std: float = 0.0,
) -> list[float]:
    """
    Predict all lap times for a full race given a strategy.

    Parameters
    ----------
    strategy_stints : List of (compound, stint_duration) tuples
    deg_model       : Fitted TyreDegModel
    noise_std       : Per-lap noise std dev

    Returns
    -------
    List of predicted lap times, one per lap.
    """
    lap_times = []
    lap_number = 1

    for compound, duration in strategy_stints:
        effective_compound = compound
        if compound not in deg_model.models:
            fallback = list(deg_model.models.keys())[0]
            log.warning(f"{compound} not in model — using {fallback}")
            effective_compound = fallback

        for tyre_age in range(1, duration + 1):
            t = predict_lap_time(
                lap_number=lap_number,
                tyre_age=tyre_age,
                compound=effective_compound,
                deg_model=deg_model,
                noise_std=noise_std,
            )
            lap_times.append(t)
            lap_number += 1

    return lap_times


def expected_lap_time_with_sc(base_lap_time: float) -> float:
    """
    Adjust expected lap time for safety car probability.
    E[lap_time] = (1 - p_sc) * base + p_sc * (base + sc_delta)
               = base + p_sc * sc_delta
    """
    return base_lap_time + SC_PROB_PER_LAP * SC_DELTA_SECONDS


def lap_time_summary(deg_model: TyreDegModel,
                     total_laps: int = RACE_LAPS) -> pd.DataFrame:
    """
    Return a DataFrame of predicted lap times per compound across the race distance.
    Useful for visualisation and sanity checking.
    """
    rows = []
    for compound in deg_model.models:
        for tyre_age in range(1, min(total_laps, 40) + 1):
            rows.append({
                "Compound": compound,
                "TyreAge": tyre_age,
                "PredictedLapTime": deg_model.predict(compound, tyre_age),
            })
    return pd.DataFrame(rows)

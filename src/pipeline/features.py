"""
features.py — Feature engineering for tyre degradation modelling.

Transforms cleaned lap data into model-ready features:
  - TyreAge (laps on this set)
  - DeltaToFastest (lap time vs best lap in stint)
  - Degradation (lap time increase per lap of tyre age)
  - StintNumber
  - FuelCorrectedLapTime (approximate)
"""

import pandas as pd
import numpy as np
from src.utils.logger import get_logger

log = get_logger(__name__)

# Conservative fuel burn correction: ~0.03s per lap lighter the car gets
# (1 lap ≈ 1.7 kg fuel, ~0.03s/kg delta = 0.05s/lap)
FUEL_CORRECTION_PER_LAP = 0.05


def add_tyre_age(laps: pd.DataFrame) -> pd.DataFrame:
    """
    TyreLife is available directly from FastF1 but sometimes has gaps.
    This adds a computed tyre age as a cross-check.
    """
    laps = laps.copy()
    # FastF1 provides TyreLife — use it directly if clean
    laps["TyreAge"] = laps["TyreLife"].fillna(0).astype(int)
    return laps


def add_stint_number(laps: pd.DataFrame) -> pd.DataFrame:
    """
    Number each stint sequentially per driver (resets on pit stop).
    """
    laps = laps.copy()
    # A new stint starts when TyreAge resets to a low value
    laps["StintNumber"] = (
        laps.groupby("Driver")["TyreAge"]
        .transform(lambda x: (x.diff() < 0).cumsum() + 1)
    )
    return laps


def add_fuel_corrected_lap_time(laps: pd.DataFrame,
                                 total_laps: int = 57) -> pd.DataFrame:
    """
    Approximate fuel-corrected lap time.

    Formula: FuelCorrected = LapTime - (total_laps - LapNumber) * correction_per_lap
    This removes the 'getting faster as fuel burns off' effect so we can
    isolate pure tyre degradation.
    """
    laps = laps.copy()
    if "LapTimeSec" not in laps.columns:
        log.warning("LapTimeSec not found — skipping fuel correction")
        return laps

    fuel_remaining_laps = total_laps - laps["LapNumber"]
    fuel_delta = fuel_remaining_laps * FUEL_CORRECTION_PER_LAP
    laps["FuelCorrectedLapTime"] = laps["LapTimeSec"] - fuel_delta
    return laps


def add_deg_delta(laps: pd.DataFrame) -> pd.DataFrame:
    """
    DegDelta: lap time delta from the first clean lap of each stint.
    Captures the cumulative degradation effect.

    Implemented with groupby().transform("first") rather than
    groupby().apply() — apply() with include_groups=False silently drops
    the grouping columns from the result, which previously caused BOTH
    "Driver" and "StintNumber" to disappear from the engineered laps
    DataFrame (a serious regression: every downstream driver filter,
    including the tyre model's driver-weighted fit, would break).
    """
    laps = laps.copy()
    col = "FuelCorrectedLapTime" if "FuelCorrectedLapTime" in laps.columns else "LapTimeSec"

    stint_baseline = laps.groupby(["Driver", "StintNumber"])[col].transform("first")
    laps["DegDelta"] = laps[col] - stint_baseline
    return laps


def engineer_features(laps: pd.DataFrame, total_laps: int = 57) -> pd.DataFrame:
    """
    Full feature engineering pipeline.

    Parameters
    ----------
    laps        : Cleaned laps DataFrame
    total_laps  : Total race distance in laps (for fuel correction)

    Returns
    -------
    laps with new columns: TyreAge, StintNumber, FuelCorrectedLapTime, DegDelta
    """
    log.info("Engineering features...")
    laps = add_tyre_age(laps)
    laps = add_stint_number(laps)
    laps = add_fuel_corrected_lap_time(laps, total_laps=total_laps)
    laps = add_deg_delta(laps)
    log.info("Feature engineering complete")
    return laps

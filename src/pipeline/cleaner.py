"""
cleaner.py — Lap data cleaning and outlier removal.

Raw FastF1 lap data contains:
  - In / out laps (slow, distort deg models)
  - Safety Car / VSC laps (artificially slow)
  - Pit laps
  - Laps with missing timing data
  - Sector time anomalies

All of these must be removed before modelling.
"""

import pandas as pd
import numpy as np
from src.utils.logger import get_logger

log = get_logger(__name__)


def remove_inaccurate_laps(laps: pd.DataFrame) -> pd.DataFrame:
    """Remove laps flagged by FastF1 as inaccurate."""
    before = len(laps)
    laps = laps[laps["IsAccurate"] == True].copy()
    log.info(f"Inaccurate laps removed: {before - len(laps)} ({len(laps)} remain)")
    return laps


def remove_sc_laps(laps: pd.DataFrame) -> pd.DataFrame:
    """
    Remove Safety Car and Virtual Safety Car laps.

    TrackStatus codes:
        1 = Clear, 2 = Yellow, 4 = SC, 6 = VSC, 7 = Red flag
    """
    before = len(laps)
    # Keep only green flag laps (TrackStatus == "1")
    laps = laps[laps["TrackStatus"] == "1"].copy()
    log.info(f"SC/VSC laps removed: {before - len(laps)} ({len(laps)} remain)")
    return laps


def remove_pit_laps(laps: pd.DataFrame) -> pd.DataFrame:
    """Remove pit-in and pit-out laps."""
    before = len(laps)
    laps = laps[laps["PitInTime"].isna() & laps["PitOutTime"].isna()].copy()
    log.info(f"Pit laps removed: {before - len(laps)} ({len(laps)} remain)")
    return laps


def remove_lap_time_outliers(laps: pd.DataFrame,
                              col: str = "LapTimeSec",
                              z_threshold: float = 2.5) -> pd.DataFrame:
    """
    Remove lap time outliers using Z-score per compound group.
    This handles e.g. a driver going off-track mid-stint.
    """
    before = len(laps)
    if col not in laps.columns:
        log.warning(f"Column {col} not found — skipping outlier removal")
        return laps

    def _filter_group(group):
        if len(group) < 3:
            return group
        mean, std = group[col].mean(), group[col].std()
        if std == 0:
            return group
        z = (group[col] - mean).abs() / std
        return group[z < z_threshold]

    laps = laps.groupby("Compound", group_keys=False).apply(_filter_group, include_groups=False).reset_index(drop=True)
    log.info(f"Outlier laps removed: {before - len(laps)} ({len(laps)} remain)")
    return laps.reset_index(drop=True)


def clean_laps(laps: pd.DataFrame,
               remove_sc: bool = True,
               remove_pits: bool = True,
               outlier_z: float = 2.5) -> pd.DataFrame:
    """
    Full cleaning pipeline. Apply in order — each step depends on the last.

    Parameters
    ----------
    laps       : Raw laps DataFrame from loader.get_laps()
    remove_sc  : Whether to drop Safety Car laps
    remove_pits: Whether to drop pit in/out laps
    outlier_z  : Z-score threshold for lap time outlier removal

    Returns
    -------
    Cleaned laps DataFrame ready for feature engineering.
    """
    log.info(f"Starting cleaning pipeline: {len(laps)} laps")
    laps = remove_inaccurate_laps(laps)
    if remove_sc:
        laps = remove_sc_laps(laps)
    if remove_pits:
        laps = remove_pit_laps(laps)
    laps = remove_lap_time_outliers(laps, z_threshold=outlier_z)
    log.info(f"Cleaning complete: {len(laps)} clean laps")
    return laps

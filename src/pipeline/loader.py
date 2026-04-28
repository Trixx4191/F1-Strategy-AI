"""
loader.py — Loads and caches FastF1 session data.

FastF1 caches downloaded data locally so subsequent runs are instant.
All downstream modules receive clean DataFrames from here.
"""

import fastf1
import pandas as pd
from pathlib import Path
from src.utils.config import CACHE_DIR, YEAR, RACE, SESSION
from src.utils.logger import get_logger

log = get_logger(__name__)


def enable_cache(cache_dir: Path = CACHE_DIR) -> None:
    """Point FastF1 at our local cache directory."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))
    log.info(f"FastF1 cache enabled at {cache_dir}")


def load_session(year: int = YEAR,
                 race: str = RACE,
                 session_type: str = SESSION) -> fastf1.core.Session:
    """
    Load a FastF1 session with all timing data.

    Parameters
    ----------
    year         : Season year (e.g. 2024)
    race         : Event name or round number (e.g. "Bahrain" or 1)
    session_type : 'R', 'Q', 'FP1', 'FP2', 'FP3', 'S' (Sprint)

    Returns
    -------
    fastf1.core.Session — fully loaded session object
    """
    enable_cache()
    log.info(f"Loading {year} {race} — session: {session_type}")
    session = fastf1.get_session(year, race, session_type)
    session.load(telemetry=False, weather=True, messages=False)
    log.info(f"Session loaded: {len(session.laps)} laps total")
    return session


def get_laps(session: fastf1.core.Session,
             driver: str | None = None) -> pd.DataFrame:
    """
    Extract laps DataFrame from session, optionally filtered to one driver.

    Columns returned (subset):
        Driver, LapNumber, LapTime, Compound, TyreLife, PitOutTime,
        PitInTime, TrackStatus, IsAccurate, Sector1Time, Sector2Time,
        Sector3Time, SpeedI1, SpeedI2, SpeedFL, SpeedST
    """
    laps = session.laps

    if driver:
        laps = laps.pick_driver(driver)
        log.info(f"Filtered to driver {driver}: {len(laps)} laps")

    # Convert timedelta columns to float seconds for modelling
    for col in ["LapTime", "Sector1Time", "Sector2Time", "Sector3Time"]:
        if col in laps.columns:
            laps[f"{col}Sec"] = laps[col].dt.total_seconds()

    return laps.reset_index(drop=True)


def get_pit_stops(session: fastf1.core.Session) -> pd.DataFrame:
    """
    Extract pit stop events with timing from the laps DataFrame.

    Returns a DataFrame with columns:
        Driver, LapNumber, PitDuration (seconds)
    """
    laps = session.laps
    pit_laps = laps[laps["PitInTime"].notna()].copy()

    if pit_laps.empty:
        log.warning("No pit stop data found in session")
        return pd.DataFrame()

    pit_laps["PitDuration"] = (
        pit_laps["PitOutTime"] - pit_laps["PitInTime"]
    ).dt.total_seconds()

    return pit_laps[["Driver", "LapNumber", "PitDuration"]].reset_index(drop=True)

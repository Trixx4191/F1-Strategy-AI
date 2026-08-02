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


def get_race_schedule(year: int, only_completed: bool = True) -> list[str]:
    """
    Fetch the list of race event names for a given season via FastF1.

    Parameters
    ----------
    year            : Season year
    only_completed  : If True (default), excludes events whose EventDate is
                       in the future — prevents selecting a GP that hasn't
                       happened yet and therefore has no session data.
                       Only affects the current (in-progress) season; past
                       seasons are entirely in the past and unaffected.

    Returns a list of event names in calendar order (e.g. ["Bahrain", "Saudi Arabia", ...]).
    Falls back to a hardcoded 2024 list if the API call fails so the UI never breaks.
    """
    try:
        schedule = fastf1.get_event_schedule(year, include_testing=False)

        if only_completed:
            today = pd.Timestamp.now().normalize()
            schedule = schedule[schedule["EventDate"] <= today]

        # 'EventName' column contains the full GP name; strip " Grand Prix" suffix
        names = schedule["EventName"].str.replace(" Grand Prix", "", regex=False).str.strip().tolist()
        log.info(f"Loaded {len(names)} completed events for {year} season")
        return names
    except Exception as e:
        log.warning(f"Could not fetch {year} schedule from FastF1: {e} — using fallback list")
        return [
            "Bahrain", "Saudi Arabia", "Australia", "Japan", "China",
            "Miami", "Emilia Romagna", "Monaco", "Canada", "Spain",
            "Austria", "Great Britain", "Hungary", "Belgium", "Netherlands",
            "Italian", "Azerbaijan", "Singapore", "United States",
            "Mexico City", "São Paulo", "Las Vegas", "Qatar", "Abu Dhabi",
        ]


def get_latest_available_year() -> int:
    """
    Determine the most recent F1 season with at least one completed race.

    Tries the current calendar year first; if that season's schedule has
    no completed events yet (e.g. it's January and pre-season testing is
    the only thing on the calendar), falls back to the previous year.
    This means the dashboard's season selector never needs a manual
    yearly bump — it tracks whatever FastF1 currently has data for.
    """
    from datetime import date
    this_year = date.today().year
    try:
        races_this_year = get_race_schedule(this_year, only_completed=True)
        if races_this_year:
            return this_year
    except Exception as e:
        log.warning(f"Could not check {this_year} season: {e}")
    return this_year - 1


def get_session_drivers(session: fastf1.core.Session) -> list[str]:
    """
    Return list of driver codes who actually participated in this session.
    Used to filter the driver selector to only relevant drivers.
    """
    try:
        return sorted(session.laps["Driver"].unique().tolist())
    except Exception:
        return []


def get_race_laps(session: fastf1.core.Session) -> int:
    """
    Return the total number of laps in the race from session data.
    Falls back to config RACE_LAPS if not available.
    """
    from src.utils.config import RACE_LAPS
    try:
        total = int(session.laps["LapNumber"].max())
        if total > 0:
            return total
    except Exception:
        pass
    return RACE_LAPS


def get_track_temp(session: fastf1.core.Session) -> dict | None:
    """
    Extract mean track/ambient temperature from session weather data.

    Returns
    -------
    {"track_temp": float, "air_temp": float, "rainfall": bool} or None
    if weather data is unavailable.
    """
    try:
        weather = session.weather_data
        if weather is None or weather.empty:
            return None
        track_temp = float(weather["TrackTemp"].mean())
        air_temp   = float(weather["AirTemp"].mean())
        rainfall   = bool(weather["Rainfall"].any()) if "Rainfall" in weather.columns else False
        return {"track_temp": round(track_temp, 1),
                "air_temp": round(air_temp, 1),
                "rainfall": rainfall}
    except Exception as e:
        log.warning(f"Could not extract weather data: {e}")
        return None


def get_final_classification(session: fastf1.core.Session, top_n: int = 5) -> pd.DataFrame:
    """
    Return the top-N finishing classification for the session.

    Used to power the "timing tower" widget — grounds the tool's output
    in what actually happened in the real race.

    Returns
    -------
    DataFrame with columns: Position, Driver, TeamName, Time, Status
    Empty DataFrame if results are unavailable.
    """
    try:
        results = session.results
        if results is None or results.empty:
            return pd.DataFrame()
        cols = [c for c in ["Position", "Abbreviation", "TeamName", "Time", "Status", "GridPosition"]
                if c in results.columns]
        out = results[cols].head(top_n).copy()
        out = out.rename(columns={"Abbreviation": "Driver"})
        return out.reset_index(drop=True)
    except Exception as e:
        log.warning(f"Could not extract classification: {e}")
        return pd.DataFrame()


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

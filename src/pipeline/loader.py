"""
loader.py — Loads and caches FastF1 session data.

FastF1 caches downloaded data locally so subsequent runs are instant.
All downstream modules receive clean DataFrames from here.
"""

import fastf1
import os
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
    if os.getenv("F1_DEMO_MODE") == "true":
        if (year, race, session_type) != (2024, "Bahrain", "R"):
            raise ValueError("Demo mode includes the 2024 Bahrain race only")
        from src.pipeline.demo import load_demo_session
        return load_demo_session()
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
    if os.getenv("F1_DEMO_MODE") == "true":
        return ["Bahrain"] if year == 2024 else []
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
    if os.getenv("F1_DEMO_MODE") == "true":
        return 2024
    from datetime import date
    this_year = date.today().year
    try:
        races_this_year = get_race_schedule(this_year, only_completed=True)
        if races_this_year:
            return this_year
    except Exception as e:
        log.warning(f"Could not check {this_year} season: {e}")
    return this_year - 1



def _normalize_team_color(raw) -> str | None:
    """FastF1 TeamColor is often '3671C6' without '#'; sometimes already hex."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    if not s.startswith("#"):
        s = "#" + s
    # expand 3-digit
    if len(s) == 4:
        s = "#" + "".join(c * 2 for c in s[1:])
    if len(s) != 7:
        return None
    return s.upper()


def get_driver_entry_list(session: fastf1.core.Session) -> list[dict]:
    """
    Year/race-accurate driver roster for the selected session.

    Pulls Abbreviation, FullName, TeamName, TeamColor, DriverNumber from
    session.results so UI mappings stay correct across seasons
    (e.g. HAM → Ferrari in 2025+, not Mercedes).

    Falls back to unique Driver codes from laps if results are empty.
    """
    entries: list[dict] = []
    try:
        results = session.results
        if results is not None and not results.empty:
            for _, r in results.iterrows():
                code = str(r.get("Abbreviation") or r.get("Driver") or "").strip().upper()[:3]
                if not code:
                    continue
                number = r.get("DriverNumber") or r.get("Number")
                try:
                    number = int(number) if pd.notna(number) else None
                except (TypeError, ValueError):
                    number = None
                entries.append({
                    "code": code,
                    "name": str(r.get("FullName") or r.get("BroadcastName") or code),
                    "team": str(r.get("TeamName") or "").strip(),
                    "team_color": _normalize_team_color(r.get("TeamColor")),
                    "number": number,
                })
            # Stable order by number then code
            entries.sort(key=lambda e: (e["number"] is None, e["number"] or 999, e["code"]))
            return entries
    except Exception as e:
        log.warning(f"Could not build entry list from results: {e}")

    # Fallback: laps only
    try:
        for code in sorted(session.laps["Driver"].unique().tolist()):
            entries.append({
                "code": str(code).upper()[:3],
                "name": str(code),
                "team": "",
                "team_color": None,
                "number": None,
            })
    except Exception:
        pass
    return entries


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


def get_final_classification(session: fastf1.core.Session, top_n: int | None = None) -> pd.DataFrame:
    """
    Return finishing classification for the session.

    Used to power the timing tower — grounds the tool's output in what
    actually happened in the real race.

    Parameters
    ----------
    top_n : If given, limit to first N positions. None = full field.

    Returns
    -------
    DataFrame with columns: Position, Driver, TeamName, Time, Status, ...
    Empty DataFrame if results are unavailable.
    """
    try:
        results = session.results
        if results is None or results.empty:
            return pd.DataFrame()
        cols = [c for c in [
            "Position", "Abbreviation", "TeamName", "Time", "Status",
            "GridPosition", "Points", "ClassifiedPosition",
        ] if c in results.columns]
        out = results[cols].copy()
        if top_n is not None:
            out = out.head(top_n)
        out = out.rename(columns={"Abbreviation": "Driver"})
        return out.reset_index(drop=True)
    except Exception as e:
        log.warning(f"Could not extract classification: {e}")
        return pd.DataFrame()


def get_timing_tower_data(session: fastf1.core.Session) -> list[dict]:
    """
    Build dense timing-tower rows for the Mission Control UI.

    Combines official classification with last-lap compound / tyre life
    from the laps DataFrame so each row carries:
      pos, driver, name, team, team_color (caller fills), gap, interval,
      compound, tyre_age, last_lap, status
    """
    rows: list[dict] = []
    try:
        results = session.results
        laps = session.laps
        if results is None or results.empty:
            return rows

        # Last known compound + tyre life per driver
        last_stint: dict[str, dict] = {}
        if laps is not None and not laps.empty:
            for drv, grp in laps.groupby("Driver"):
                last = grp.sort_values("LapNumber").iloc[-1]
                last_stint[str(drv)] = {
                    "compound": str(last.get("Compound") or ""),
                    "tyre_age": int(last["TyreLife"]) if pd.notna(last.get("TyreLife")) else None,
                    "last_lap": float(last["LapTime"].total_seconds())
                    if pd.notna(last.get("LapTime")) else None,
                }

        for _, r in results.iterrows():
            code = str(r.get("Abbreviation") or r.get("Driver") or "")[:3]
            pos = r.get("Position")
            try:
                pos = int(pos) if pd.notna(pos) else None
            except (TypeError, ValueError):
                pos = None

            stint = last_stint.get(code, {})
            time_val = r.get("Time")
            gap = None
            if pos == 1:
                gap = 0.0
            elif pd.notna(time_val):
                try:
                    gap = float(time_val.total_seconds())
                except Exception:
                    gap = None

            _num = None
            try:
                if pd.notna(r.get("DriverNumber")):
                    _num = int(r.get("DriverNumber"))
            except (TypeError, ValueError):
                _num = None
            rows.append({
                "pos": pos,
                "driver": code,
                "name": str(r.get("FullName") or code),
                "team": str(r.get("TeamName") or ""),
                "team_color": _normalize_team_color(r.get("TeamColor")),
                "number": _num,
                "gap": gap,
                "interval": None,
                "compound": stint.get("compound"),
                "tyre_age": stint.get("tyre_age"),
                "last_lap": stint.get("last_lap"),
                "status": str(r.get("Status") or ""),
            })

        # Sort by position (None at end)
        rows.sort(key=lambda x: (x["pos"] is None, x["pos"] or 999))
        return rows
    except Exception as e:
        log.warning(f"Could not build timing tower data: {e}")
        return rows


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


def get_circuit_outline(session: fastf1.core.Session) -> dict:
    """
    Extract circuit geometry for the selected GP from FastF1 — no hardcoding.

    Uses session.get_circuit_info() corner coordinates when available.
    Returns:
      {
        "name": str,
        "points": list[{"x": float, "y": float}],   # normalised 0–1
        "corners": list[{"x": float, "y": float, "number": int}],
      }
    Empty points if geometry is unavailable for that session.
    """
    if hasattr(session, "demo_circuit"):
        return session.demo_circuit
    out = {"name": "", "points": [], "corners": []}
    try:
        event = getattr(session, "event", None)
        if event is not None:
            out["name"] = str(event.get("Location") or event.get("EventName") or "")

        info = session.get_circuit_info()
        if info is None:
            return out

        corners = getattr(info, "corners", None)
        if corners is None or (hasattr(corners, "empty") and corners.empty):
            return out

        # corners typically has X, Y (or x, y) in metres
        xcol = "X" if "X" in corners.columns else ("x" if "x" in corners.columns else None)
        ycol = "Y" if "Y" in corners.columns else ("y" if "y" in corners.columns else None)
        if xcol is None or ycol is None:
            return out

        xs = corners[xcol].astype(float).tolist()
        ys = corners[ycol].astype(float).tolist()
        if not xs:
            return out

        # Close the loop
        if xs[0] != xs[-1] or ys[0] != ys[-1]:
            xs = xs + [xs[0]]
            ys = ys + [ys[0]]

        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        dx = max(maxx - minx, 1e-9)
        dy = max(maxy - miny, 1e-9)
        # Keep aspect ratio inside 0–1 box with padding
        pad = 0.08
        scale = (1 - 2 * pad) / max(dx, dy)

        def norm(x, y):
            nx = pad + (x - minx) * scale + (1 - 2 * pad - dx * scale) / 2
            ny = pad + (y - miny) * scale + (1 - 2 * pad - dy * scale) / 2
            # SVG y grows downward — flip for map-like orientation
            return {"x": float(nx), "y": float(1 - ny)}

        out["points"] = [norm(x, y) for x, y in zip(xs, ys)]
        numbers = corners["Number"].tolist() if "Number" in corners.columns else list(range(1, len(xs)))
        out["corners"] = [
            {**norm(float(corners.iloc[i][xcol]), float(corners.iloc[i][ycol])),
             "number": int(numbers[i]) if i < len(numbers) else i + 1}
            for i in range(len(corners))
        ]
        log.info(f"Circuit outline loaded: {len(out['points'])} points ({out['name']})")
    except Exception as e:
        log.warning(f"Could not extract circuit outline: {e}")
    return out

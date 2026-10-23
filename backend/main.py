"""
F1 Strategy AI — FastAPI backend (full feature parity with dashboard.py).
"""

from __future__ import annotations

# matplotlib.use("Agg") MUST run before any other import touches matplotlib
# (several src.visualisation modules import pyplot at module load time).
# Without this, matplotlib auto-detects a backend on first use — on a
# server with no display this usually resolves to Agg anyway, but the
# auto-detection probes for GUI toolkits (Qt/Tk) first, which is slower
# and non-deterministic across deployment environments. Setting it
# explicitly, first, makes backend startup faster and consistent.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import sys
import traceback
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os
from pydantic import BaseModel, Field
import io, csv, json, hashlib

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.loader import (
    load_session, get_laps, get_pit_stops, get_race_schedule,
    get_race_laps, get_track_temp, get_latest_available_year,
    get_timing_tower_data, get_circuit_outline, get_session_drivers, get_driver_entry_list,
)
from src.pipeline.cleaner import clean_laps

# ── Session cache ────────────────────────────────────────────────────────────
#
# Measured problem: selecting a race calls /api/session, then clicking "Run
# Simulation" calls /api/simulate — both independently call load_session()
# for the same (year, race). Measured on real 2024 Bahrain data: ~2000ms for
# the session-only load, then ANOTHER ~2900ms for /api/simulate which
# includes its own full session reload before doing any actual simulation
# work. Same redundancy exists across /api/undercut/plot, /api/overcut/plot,
# and /api/rival-analysis when a user explores multiple tabs for one race.
#
# Fix: a small in-process cache keyed by (year, race), bounded to the last
# few sessions so memory doesn't grow unbounded across a long-running
# server. A lock guards the cache structure itself (insertion/eviction),
# but load_session() runs OUTSIDE the lock — holding it during a ~2s load
# would serialize requests for genuinely DIFFERENT races too, not just
# duplicate requests for the same one. Two concurrent requests for the same
# uncached (year, race) can each still trigger their own load in the rare
# race-condition case; the second result simply overwrites the first in the
# cache. For a single-user app this is a low-cost edge case, not worth the
# complexity of a per-key lock to fully eliminate.
#
# This assumes completed, historical race data, which never changes once a
# session has happened — safe to cache indefinitely (bounded by size, not
# time). Not appropriate for a genuinely live/in-progress session where new
# laps could still be arriving, but get_race_schedule's only_completed=True
# filtering already keeps this app scoped to finished races.
import threading
from collections import OrderedDict

_SESSION_CACHE_MAX = 4
_session_cache: "OrderedDict[tuple[int, str], Any]" = OrderedDict()
_session_cache_lock = threading.Lock()


def _get_cached_session(year: int, race: str):
    key = (year, race)
    with _session_cache_lock:
        cached = _session_cache.get(key)
        if cached is not None:
            _session_cache.move_to_end(key)
            return cached

    session = load_session(year, race)

    with _session_cache_lock:
        _session_cache[key] = session
        _session_cache.move_to_end(key)
        while len(_session_cache) > _SESSION_CACHE_MAX:
            _session_cache.popitem(last=False)

    return session
from src.pipeline.features import engineer_features
from src.models.tyre_deg import TyreDegModel
from src.models.pit_loss import get_pit_loss
from src.simulator.strategy import (
    Strategy, Stint,
    generate_one_stop_strategies, generate_two_stop_strategies,
)
from src.simulator.monte_carlo import run_monte_carlo, run_rival_monte_carlo
from src.simulator.race_sim import simulate_race, simulate_race_with_rival
from src.simulator.rival import RivalState, scan_undercut_window, scan_overcut_window
from src.utils.config import COMPOUNDS
from src.utils.config import OUTPUTS_DIR
from src.visualisation.strategy_plots import plot_undercut_window, plot_lap_trace
from src.visualisation.rival_plots import plot_undercut_ev_timeline
from src.visualisation.rival_plots import plot_undercut_vs_overcut

app = FastAPI(title="F1 Strategy AI", version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


class SimulateRequest(BaseModel):
    year: int
    race: str
    driver: str = "VER"
    rival: str = "NOR"
    n_simulations: int = Field(default=500, ge=50, le=2000)
    strategy_type: str = Field(default="Both", pattern="^(1-stop|2-stop|Both)$")
    noise_std: float = Field(default=0.3, ge=0.0, le=2.0)
    use_live_temp: bool = True
    track_temp_override: Optional[float] = None
    # Optional: when the frontend already has a /api/simulate response in
    # memory (the normal case — a user runs a simulation, looks at the
    # dashboard, then clicks "export CSV"), it can pass that response's
    # `strategies` array straight through here. This lets /api/simulate/csv
    # skip session loading, model fitting, and a full Monte Carlo re-run
    # entirely — previously every CSV export re-ran the whole pipeline
    # from scratch just to re-derive a table it already had.
    precomputed_strategies: Optional[list[dict]] = None


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "f1-strategy-ai"}


@app.get("/api/demo/run")
def demo_run():
    path = ROOT / "data/demo/default-run.json"
    if os.getenv("F1_DEMO_MODE") != "true" or not path.exists():
        raise HTTPException(404, detail="Precomputed demo is unavailable")
    return FileResponse(path, media_type="application/json")


# Simple on-disk cache for generated plots
PLOT_CACHE = OUTPUTS_DIR / "plot_cache"
PLOT_CACHE.mkdir(parents=True, exist_ok=True)


def _make_key(obj: Any) -> str:
    try:
        s = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        s = str(obj)
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _cached_png_response(key: str, buf: io.BytesIO) -> StreamingResponse:
    path = PLOT_CACHE / f"{key}.png"
    if path.exists():
        return StreamingResponse(path.open("rb"), media_type="image/png")
    # write buffer to cache file and return buffer
    with path.open("wb") as f:
        f.write(buf.getvalue())
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@app.get("/api/plot/{name}")
def get_cached_plot(name: str):
    # Only allow hex32.png filenames for safety
    if not name.endswith('.png') or len(name) != 36:
        raise HTTPException(400, detail="Invalid plot name")
    if any(c not in '0123456789abcdef.' for c in name):
        raise HTTPException(400, detail="Invalid plot name")
    path = PLOT_CACHE / name
    if not path.exists():
        raise HTTPException(404, detail="Plot not found")
    return StreamingResponse(path.open('rb'), media_type='image/png')


@app.get("/api/seasons/latest")
def latest_season():
    try:
        return {"year": get_latest_available_year()}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/seasons/{year}/races")
def list_races(year: int, only_completed: bool = True):
    try:
        return {"year": year, "races": get_race_schedule(year, only_completed=only_completed)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/session")
def get_session_data(year: int = Query(...), race: str = Query(...)):
    try:
        session = _get_cached_session(year, race)
        drivers = get_driver_entry_list(session)
        return {
            "year": year, "race": race,
            "race_laps": get_race_laps(session) or 57,
            "timing": get_timing_tower_data(session),
            "circuit": get_circuit_outline(session),
            "weather": get_track_temp(session),
            "session_drivers": [d["code"] for d in drivers],
            "drivers": drivers,
        }
    except Exception as e:
        raise HTTPException(502, detail=f"Failed to load session {year} {race}: {e}")


def _tyre_curves(deg_model: TyreDegModel, max_age: int | None = None) -> list[dict]:
    """
    Predicted lap time vs tyre age from the fitted piecewise model.

    max_age defaults to the largest tyre age seen in the fitted compound
    models (plus a small pad), so we do not extrapolate far beyond data.
    """
    curves = []
    fitted = list(deg_model.models.keys()) if hasattr(deg_model, "models") else []
    if not fitted:
        return curves

    # Derive a sensible age range from the fitted CompoundModel data extents
    data_max = 1
    for c in fitted:
        cm = deg_model.models.get(c)
        if cm is not None and hasattr(cm, "breaks") and cm.breaks is not None:
            try:
                data_max = max(data_max, int(float(cm.breaks[-1])))
            except Exception:
                pass
    if max_age is None:
        max_age = min(max(data_max + 3, 15), 40)
    ages = list(range(1, max_age + 1))

    for c in COMPOUNDS:
        if c not in fitted:
            continue
        try:
            preds = [float(deg_model.predict(c, a)) for a in ages]
            cliff = deg_model.cliff_lap(c)
            ci = deg_model.cliff_ci(c)
            slopes = deg_model.phase_slopes(c) or {}
            curves.append({
                "compound": c,
                "ages": ages,
                "lap_times": preds,
                "cliff_lap": float(cliff) if cliff is not None else None,
                "cliff_ci": [float(ci[0]), float(ci[1])] if ci else None,
                "phase_slopes": {k: float(v) for k, v in slopes.items()},
                "fit_mode": deg_model.fit_mode(c),
                "max_age_data": data_max,
            })
        except Exception:
            traceback.print_exc()
            continue
    return curves


def _stint_scatter(laps: pd.DataFrame, driver: str) -> list[dict]:
    """
    Actual clean-lap points for the selected driver, aligned with the model
    training data (post clean_laps + engineer_features).

    Uses FuelCorrectedLapTime when available so scatter matches the curve
    the piecewise model was fit on. TyreAge < 1 is dropped (fillna artefact).
    """
    pts = []
    try:
        dl = laps[laps["Driver"] == driver].copy() if "Driver" in laps.columns else laps.copy()
        time_col = "FuelCorrectedLapTime" if "FuelCorrectedLapTime" in dl.columns else "LapTimeSec"
        if time_col not in dl.columns or "TyreAge" not in dl.columns:
            return pts
        dl = dl.dropna(subset=["TyreAge", time_col, "Compound"])
        dl = dl[dl["TyreAge"] >= 1]
        for _, r in dl.iterrows():
            pts.append({
                "tyre_age": int(r["TyreAge"]),
                "lap_time": float(r[time_col]),
                "compound": str(r.get("Compound") or "").upper(),
                "lap_number": int(r["LapNumber"]) if pd.notna(r.get("LapNumber")) else None,
                "time_basis": time_col,
            })
    except Exception:
        traceback.print_exc()
    return pts


def _strategy_rows(mc_df: pd.DataFrame) -> list[dict]:
    rows = []
    if mc_df is None or mc_df.empty:
        return rows
    for rank, (_, r) in enumerate(mc_df.sort_values("mean_time").iterrows(), 1):
        compounds = r.get("compounds")
        obj = r.get("strategy_obj")
        if not compounds and obj is not None and hasattr(obj, "stints"):
            compounds = [s.compound for s in obj.stints]
        if isinstance(compounds, str):
            compounds = [c.strip() for c in compounds.replace("→", ",").split(",") if c.strip()]
        pit_laps = []
        if obj is not None and hasattr(obj, "stints") and len(obj.stints) > 1:
            cum = 0
            for stint in obj.stints[:-1]:
                cum += stint.duration
                pit_laps.append(cum)
        rows.append({
            "rank": rank,
            "strategy": str(r.get("strategy", "")),
            "compound_sequence": list(compounds or []),
            "pit_laps": pit_laps,
            "pit_count": int(r["pit_count"]) if r.get("pit_count") is not None else len(pit_laps),
            "mean_time": float(r["mean_time"]) if r.get("mean_time") is not None else None,
            "std_time": float(r["std_time"]) if r.get("std_time") is not None else None,
            "p10": float(r["p10"]) if r.get("p10") is not None else None,
            "p50": float(r["p50"]) if r.get("p50") is not None else None,
            "p90": float(r["p90"]) if r.get("p90") is not None else None,
            "win_rate": float(r["win_rate"]) if r.get("win_rate") is not None else None,
        })
    return rows


def _lap_traces(mc_df: pd.DataFrame, deg_model: TyreDegModel, pit_loss: float, n: int = 3) -> list[dict]:
    traces = []
    if mc_df is None or mc_df.empty:
        return traces
    for _, r in mc_df.sort_values("mean_time").head(n).iterrows():
        obj = r.get("strategy_obj")
        if obj is None:
            continue
        try:
            res = simulate_race(obj, deg_model, pit_loss, noise_std=0.0)
            traces.append({
                "label": str(r.get("strategy", "")),
                "lap_times": res["lap_times"],
                "pit_laps": res["pit_laps"],
                "total_time": res["total_time"],
            })
        except Exception:
            continue
    return traces


def _undercut_heatmap(mc_df: pd.DataFrame) -> list[dict]:
    """Pit-lap vs mean_time for 1-stop strategies (for heatmap/scatter)."""
    cells = []
    if mc_df is None or mc_df.empty:
        return cells
    one = mc_df[mc_df["pit_count"] == 1] if "pit_count" in mc_df.columns else mc_df
    for _, r in one.iterrows():
        obj = r.get("strategy_obj")
        pit = None
        compounds = []
        if obj is not None and hasattr(obj, "stints") and len(obj.stints) >= 2:
            pit = obj.stints[0].duration
            compounds = [s.compound for s in obj.stints]
        cells.append({
            "pit_lap": pit,
            "compounds": compounds,
            "pair": "→".join(compounds) if compounds else str(r.get("strategy", "")),
            "mean_time": float(r["mean_time"]) if r.get("mean_time") is not None else None,
            "win_rate": float(r["win_rate"]) if r.get("win_rate") is not None else None,
        })
    return cells


def _backtest(laps_raw: pd.DataFrame, driver: str, mc_df: pd.DataFrame,
              deg_model: TyreDegModel, pit_loss: float) -> dict | None:
    """
    Reconstruct the driver's actual compound sequence from FastF1 TyreLife
    resets (same logic as dashboard.py), then deterministically resimulate
    actual vs AI-optimal under the fitted model for an apples-to-apples delta.
    """
    try:
        if mc_df is None or mc_df.empty:
            return None
        dl = laps_raw[laps_raw["Driver"] == driver].copy()
        if dl.empty or "Compound" not in dl.columns or "TyreLife" not in dl.columns:
            return None
        dl = dl.sort_values("LapNumber").reset_index(drop=True)
        # New stint when tyre life drops (fresh set) — matches features.add_stint_number
        tyre_life = pd.to_numeric(dl["TyreLife"], errors="coerce")
        dl["_sc"] = (tyre_life.diff() < 0).fillna(False).cumsum()
        actual_stints: list[tuple[str, int]] = []
        for _, grp in dl.groupby("_sc"):
            compounds = grp["Compound"].dropna()
            if compounds.empty:
                continue
            cmpd = str(compounds.mode().iloc[0]).upper()
            dur = int(len(grp))
            if dur > 0 and cmpd:
                actual_stints.append((cmpd, dur))
        if len(actual_stints) < 2:
            return None
        actual_strat = Strategy(stints=[Stint(c, d) for c, d in actual_stints])
        actual_res = simulate_race(actual_strat, deg_model, pit_loss, noise_std=0.0)
        optimal_obj = mc_df.iloc[0]["strategy_obj"]
        optimal_res = simulate_race(optimal_obj, deg_model, pit_loss, noise_std=0.0)
        delta = actual_res["total_time"] - optimal_res["total_time"]
        return {
            "actual": {
                "label": f"Actual ({driver})",
                "strategy": str(actual_strat),
                "compound_sequence": [c for c, _ in actual_stints],
                "pit_laps": actual_res["pit_laps"],
                "total_time": actual_res["total_time"],
                "lap_times": actual_res["lap_times"],
            },
            "optimal": {
                "label": "AI Optimal",
                "strategy": str(mc_df.iloc[0].get("strategy", "")),
                "pit_laps": optimal_res["pit_laps"],
                "total_time": optimal_res["total_time"],
                "lap_times": optimal_res["lap_times"],
                "win_rate": float(mc_df.iloc[0]["win_rate"]) if mc_df.iloc[0].get("win_rate") is not None else None,
            },
            "delta_seconds": delta,
            "verdict": "suboptimal" if delta > 0.5 else ("near-optimal" if abs(delta) <= 0.5 else "optimal"),
        }
    except Exception:
        traceback.print_exc()
        return None


def _pick_fitted_compound(deg_model: TyreDegModel, preferred: str) -> str | None:
    """
    Return `preferred` if TyreDegModel actually fitted a curve for it,
    otherwise fall back to whichever compound the model DID fit (arbitrary
    but deterministic — sorted order). Returns None only if the model has
    no fitted compounds at all (should not happen in practice, but this
    keeps the function total rather than raising).

    Guards against calling deg_model.predict() on a compound the driver
    never ran that race — e.g. a driver who ran SOFT/HARD only has no
    MEDIUM curve, so blindly defaulting to "MEDIUM" (as several call sites
    previously did) raises ValueError deep inside the rival/undercut scan,
    silently swallowed by a broad try/except and surfacing as the rival
    engine mysteriously returning all-None results.
    """
    fitted = sorted(deg_model.models.keys())
    if not fitted:
        return None
    p = str(preferred).upper()
    return p if p in fitted else fitted[0]


def _pick_switch_compound(deg_model: TyreDegModel, current: str, preferred_new: str | None = None) -> str | None:
    """
    Return a fitted compound different from `current`, for undercut/overcut
    scans that model switching tyres. Tries `preferred_new` first if given
    and fitted; otherwise picks any other fitted compound. Returns None if
    fewer than 2 compounds were fitted this session (no valid switch
    exists — e.g. a driver who ran only one compound all race) so callers
    can skip the switch-dependent analysis rather than crash or fabricate
    a result from an unfitted curve.
    """
    fitted = sorted(deg_model.models.keys())
    current_u = str(current).upper()
    others = [c for c in fitted if c != current_u]
    if not others:
        return None
    if preferred_new:
        p = str(preferred_new).upper()
        if p in others:
            return p
    return others[0]


def _scan_to_list(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    out = []
    for _, r in df.iterrows():
        out.append({
            "lap": int(r["lap"]),
            "mean_ev": float(r["mean_ev"]),
            "p10_ev": float(r["p10_ev"]),
            "p50_ev": float(r["p50_ev"]),
            "p90_ev": float(r["p90_ev"]),
            "win_rate": float(r["win_rate"]),
            "recommend": bool(r["recommend"]),
        })
    return out


@app.post("/api/simulate")
def simulate(req: SimulateRequest) -> dict[str, Any]:
    # Session/data loading gets its own try block so a FastF1 upstream
    # failure (no data for this race, network issue) reports as 502 —
    # matching /api/session — rather than collapsing into the same 500
    # used below for a genuine bug in our own simulation/transform code.
    try:
        session = _get_cached_session(req.year, req.race)
        laps_raw = get_laps(session)
        pit_stops = get_pit_stops(session)
        race_laps = get_race_laps(session) or 57
        timing = get_timing_tower_data(session)
        circuit = get_circuit_outline(session)
        weather = get_track_temp(session)
        drivers = get_driver_entry_list(session)
    except Exception as e:
        raise HTTPException(502, detail=f"Failed to load session {req.year} {req.race}: {e}")

    try:
        track_temp = None
        if req.use_live_temp and weather:
            track_temp = weather.get("track_temp")
        elif req.track_temp_override is not None:
            track_temp = req.track_temp_override

        # Fuel correction must use the real race distance, not a hardcoded 57
        cleaned = clean_laps(laps_raw)
        laps = engineer_features(cleaned, total_laps=race_laps)
        deg_model = TyreDegModel()
        deg_model.fit(laps, driver=req.driver)
        if track_temp is not None:
            deg_model.set_track_temp(float(track_temp))

        pit_loss = get_pit_loss(pit_stops)

        strategies = []
        if req.strategy_type in ("1-stop", "Both"):
            strategies.extend(generate_one_stop_strategies(total_laps=race_laps))
        if req.strategy_type in ("2-stop", "Both"):
            strategies.extend(generate_two_stop_strategies(total_laps=race_laps))

        mc_df = run_monte_carlo(
            strategies, deg_model, pit_loss=pit_loss,
            n_simulations=req.n_simulations, noise_std=req.noise_std,
        )

        strat_rows = _strategy_rows(mc_df)

        # Scatter first so curve x-range tracks observed tyre ages
        stint_scatter = _stint_scatter(laps, req.driver)
        scatter_max = max((p["tyre_age"] for p in stint_scatter), default=0)
        tyre_curves = _tyre_curves(
            deg_model,
            max_age=min(max(scatter_max + 2, 12), 40) if scatter_max else None,
        )

        tyre_summary = []
        phase_slopes = []
        for c in tyre_curves:
            ci = c.get("cliff_ci")
            tyre_summary.append({
                "compound": c["compound"],
                "cliff_lap": c["cliff_lap"],
                "cliff_ci_low": ci[0] if ci else None,
                "cliff_ci_high": ci[1] if ci else None,
                "fit_mode": c.get("fit_mode"),
            })
            phase_slopes.append({"compound": c["compound"], **(c.get("phase_slopes") or {})})


        # 1-stop vs 2-stop summary (dashboard Results tab)
        stop_comparison = None
        try:
            if mc_df is None or mc_df.empty:
                raise ValueError("no mc")
            one = mc_df[mc_df["pit_count"] == 1] if "pit_count" in mc_df.columns else mc_df.iloc[0:0]
            two = mc_df[mc_df["pit_count"] == 2] if "pit_count" in mc_df.columns else mc_df.iloc[0:0]
            b1 = one.iloc[0] if len(one) else None
            b2 = two.iloc[0] if len(two) else None
            if b1 is not None or b2 is not None:
                stop_comparison = {
                    "best_1stop": None if b1 is None else {
                        "strategy": str(b1.get("strategy", "")),
                        "mean_time": float(b1["mean_time"]),
                        "win_rate": float(b1["win_rate"]) if b1.get("win_rate") is not None else None,
                        "std_time": float(b1["std_time"]) if b1.get("std_time") is not None else None,
                    },
                    "best_2stop": None if b2 is None else {
                        "strategy": str(b2.get("strategy", "")),
                        "mean_time": float(b2["mean_time"]),
                        "win_rate": float(b2["win_rate"]) if b2.get("win_rate") is not None else None,
                        "std_time": float(b2["std_time"]) if b2.get("std_time") is not None else None,
                    },
                }
                if b1 is not None and b2 is not None:
                    diff = float(b2["mean_time"]) - float(b1["mean_time"])
                    stop_comparison["faster"] = "1-stop" if diff > 0 else "2-stop"
                    stop_comparison["delta_seconds"] = abs(diff)
        except Exception:
            traceback.print_exc()

        lap_traces = _lap_traces(mc_df, deg_model, pit_loss, n=3)
        undercut_heatmap = _undercut_heatmap(mc_df)
        backtest = _backtest(laps_raw, req.driver, mc_df, deg_model, pit_loss)

        # Generate and cache backtest plot PNG and expose a URL in response
        try:
            if backtest and isinstance(backtest, dict):
                a = backtest.get("actual") or {}
                o = backtest.get("optimal") or {}
                key = _make_key({"type": "backtest", "a": a, "o": o})
                p = PLOT_CACHE / f"{key}.png"
                if not p.exists():
                    try:
                        fig = plot_lap_trace([a, o], labels=[a.get("label", "Actual"), o.get("label", "AI Optimal")], save=False)
                        if fig is not None:
                            fig.savefig(str(p), format="png", dpi=150, bbox_inches="tight")
                            plt.close(fig)
                    except Exception:
                        traceback.print_exc()
                backtest_plot_url = f"/api/plot/{key}.png"
                backtest["plot_url"] = backtest_plot_url
        except Exception:
            traceback.print_exc()

        # Rival full timelines
        rival_result: dict[str, Any] = {
            "rival_code": req.rival,
            "undercut_best_ev": None, "undercut_best_lap": None,
            "overcut_best_ev": None, "overcut_best_lap": None,
            "win_rate_under": None, "win_rate_over": None,
            "recommended_window": None,
            "undercut_timeline": [], "overcut_timeline": [],
        }
        try:
            our_row = next((r for r in timing if r.get("driver") == req.driver), None)
            riv_row = next((r for r in timing if r.get("driver") == req.rival), None)
            our_compound_raw = (our_row or {}).get("compound") or "MEDIUM"
            our_age = int((our_row or {}).get("tyre_age") or 8)
            riv_compound_raw = (riv_row or {}).get("compound") or "MEDIUM"
            riv_age = int((riv_row or {}).get("tyre_age") or 10)
            our_gap = (our_row or {}).get("gap")
            riv_gap = (riv_row or {}).get("gap")
            gap_to_us = (
                float(riv_gap) - float(our_gap)
                if our_gap is not None and riv_gap is not None else 2.5
            )

            # Only use compounds the deg model actually fitted this
            # session — e.g. a driver who ran SOFT/HARD only has no MEDIUM
            # curve, and blindly defaulting to "MEDIUM" here previously
            # crashed deg_model.predict() deep inside the scan functions,
            # silently caught by the try/except below and surfacing as the
            # rival engine mysteriously returning all-None results.
            our_compound = _pick_fitted_compound(deg_model, our_compound_raw)
            riv_compound = _pick_fitted_compound(deg_model, riv_compound_raw) or our_compound
            new_compound = _pick_switch_compound(deg_model, our_compound) if our_compound else None

            if our_compound is None or new_compound is None:
                # Not enough compound diversity fitted this session to
                # model a tyre switch — leave rival_result at its default
                # (all-None) rather than raise. This is an honest "not
                # enough data" state, not a bug.
                raise RuntimeError(
                    "Insufficient fitted compounds for undercut/overcut analysis "
                    f"(driver ran: {sorted(deg_model.models.keys())})"
                )

            rival_state = RivalState(
                driver=req.rival,
                compound=str(riv_compound).upper(),
                tyre_age=max(1, riv_age),
                gap_to_us=gap_to_us,
            )
            from_lap = max(8, race_laps // 4)
            to_lap = min(race_laps - 8, race_laps // 2 + 5)
            n_riv = min(150, req.n_simulations)
            under_df = scan_undercut_window(
                from_lap=from_lap, to_lap=to_lap,
                our_compound=str(our_compound).upper(),
                our_tyre_age_at_from_lap=max(1, our_age),
                new_compound=new_compound,
                rival=rival_state, deg_model=deg_model, pit_loss=pit_loss,
                n_simulations=n_riv, noise_std=req.noise_std,
            )
            over_df = scan_overcut_window(
                from_lap=from_lap, to_lap=to_lap,
                our_compound=str(our_compound).upper(),
                our_tyre_age_at_from_lap=max(1, our_age),
                new_compound=new_compound,
                rival=rival_state, deg_model=deg_model, pit_loss=pit_loss,
                n_simulations=n_riv, noise_std=req.noise_std,
            )
            rival_result["undercut_timeline"] = _scan_to_list(under_df)
            rival_result["overcut_timeline"] = _scan_to_list(over_df)
            if under_df is not None and not under_df.empty:
                best_u = under_df.loc[under_df["mean_ev"].idxmax()]
                rival_result["undercut_best_ev"] = float(best_u["mean_ev"])
                rival_result["undercut_best_lap"] = int(best_u["lap"])
                rival_result["win_rate_under"] = float(best_u["win_rate"])
                rec = under_df[under_df["recommend"] == True]
                if not rec.empty:
                    rival_result["recommended_window"] = [int(rec["lap"].min()), int(rec["lap"].max())]
            if over_df is not None and not over_df.empty:
                best_o = over_df.loc[over_df["mean_ev"].idxmax()]
                rival_result["overcut_best_ev"] = float(best_o["mean_ev"])
                rival_result["overcut_best_lap"] = int(best_o["lap"])
                rival_result["win_rate_over"] = float(best_o["win_rate"])
        except Exception:
            traceback.print_exc()

        # Model summary table
        try:
            sumdf = deg_model.summary()
            model_summary = sumdf.replace({np.nan: None}).to_dict(orient="records")
        except Exception:
            model_summary = []

        return {
            "year": req.year, "race": req.race, "driver": req.driver,
            "race_laps": race_laps,
            "timing": timing, "circuit": circuit, "weather": weather,
            "drivers": drivers,
            "session_drivers": [d["code"] for d in drivers],
            "strategies": strat_rows,
            "tyre_summary": tyre_summary,
            "tyre_curves": tyre_curves,
            "phase_slopes": phase_slopes,
            "stint_scatter": stint_scatter,
            "lap_traces": lap_traces,
            "undercut_heatmap": undercut_heatmap,
            "backtest": backtest,
            "model_summary": model_summary,
            "rival": rival_result,
            "n_simulations": req.n_simulations,
            "pit_loss": pit_loss,
            "stop_comparison": stop_comparison,
            "optimal_strategy": strat_rows[0] if strat_rows else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, detail=f"Simulation failed: {e}")


@app.post("/api/simulate/csv")
def simulate_csv(req: SimulateRequest):
    """Return strategies as a CSV attachment.

    If req.precomputed_strategies is provided, uses it directly — this is
    the fast, expected path (frontend already ran /api/simulate to render
    the dashboard, then the user clicked export). Falls back to a full
    simulate(req) re-run only when no precomputed data is supplied, so
    the endpoint still works standalone (e.g. direct API testing) without
    silently breaking.
    """
    try:
        if req.precomputed_strategies is not None:
            strategies = req.precomputed_strategies
        else:
            result = simulate(req)
            strategies = result.get("strategies") or []

        # Build CSV in-memory
        buf = io.StringIO()
        writer = csv.writer(buf)
        cols = ["rank", "strategy", "compound_sequence", "pit_laps", "pit_count", "mean_time", "std_time", "p10", "p50", "p90", "win_rate"]
        writer.writerow(cols)
        for s in strategies:
            writer.writerow([
                s.get("rank"),
                s.get("strategy") or ",".join(s.get("compound_sequence") or []),
                "→".join(s.get("compound_sequence") or []),
                " ".join(str(x) for x in (s.get("pit_laps") or [])),
                s.get("pit_count"),
                s.get("mean_time"),
                s.get("std_time"),
                s.get("p10"),
                s.get("p50"),
                s.get("p90"),
                s.get("win_rate"),
            ])
        buf.seek(0)
        fname = f"f1_strategy_{req.year}_{req.race}_{req.driver}.csv"
        return StreamingResponse(buf, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=\"{fname}\""})
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, detail=f"CSV export failed: {e}")



@app.post("/api/undercut/plot")
def undercut_plot(body: dict):
    """Generate the exact matplotlib undercut window figure as PNG.

    If the caller provides a precomputed `mc_results` list (the same
    `strategies` array returned by `/api/simulate`), use that DataFrame
    to build the plot and avoid rerunning Monte Carlo.
    """
    try:
        mc_results = body.get("mc_results")
        race_laps = body.get("race_laps") or body.get("race_laps_override") or 0

        # Build cache key
        if mc_results:
            # Build DataFrame from provided strategy rows
            df = pd.DataFrame(mc_results)
            # Ensure 'compounds' column exists for legacy plotting
            if "compounds" not in df.columns and "compound_sequence" in df.columns:
                df["compounds"] = df["compound_sequence"].apply(lambda s: "→".join(s) if isinstance(s, (list, tuple)) else (s or ""))
            key = _make_key({"type": "undercut", "race_laps": int(race_laps) if race_laps else 0, "mc": mc_results})
            p = PLOT_CACHE / f"{key}.png"
            if p.exists():
                return StreamingResponse(p.open("rb"), media_type="image/png")
            fig = plot_undercut_window(df, int(race_laps) if race_laps else 0, save=False)
        else:
            # Fallback: run minimal steps (legacy behaviour)
            year = int(body.get("year", 0))
            race = body.get("race")
            driver = body.get("driver", "VER")
            n_simulations = int(body.get("n_simulations", 200))
            noise_std = float(body.get("noise_std", 0.3))
            strategy_type = body.get("strategy_type", "Both")

            session = _get_cached_session(year, race)
            laps_raw = get_laps(session)
            pit_stops = get_pit_stops(session)
            race_laps = get_race_laps(session) or 57

            cleaned = clean_laps(laps_raw)
            laps = engineer_features(cleaned, total_laps=race_laps)
            deg_model = TyreDegModel()
            deg_model.fit(laps, driver=driver)
            weather = get_track_temp(session)
            if weather:
                deg_model.set_track_temp(float(weather.get("track_temp")))

            pit_loss = get_pit_loss(pit_stops)
            strategies = []
            if strategy_type in ("1-stop", "Both"):
                strategies.extend(generate_one_stop_strategies(total_laps=race_laps))
            if strategy_type in ("2-stop", "Both"):
                strategies.extend(generate_two_stop_strategies(total_laps=race_laps))

            mc_df = run_monte_carlo(
                strategies, deg_model, pit_loss=pit_loss,
                n_simulations=n_simulations, noise_std=noise_std,
            )
            # cache key for fallback path
            key = _make_key({
                "type": "undercut", "year": year, "race": race, "driver": driver,
                "n_simulations": n_simulations, "noise_std": noise_std,
                "strategy_type": strategy_type,
            })
            p = PLOT_CACHE / f"{key}.png"
            if p.exists():
                return StreamingResponse(p.open("rb"), media_type="image/png")
            fig = plot_undercut_window(mc_df, race_laps, save=False)

        if fig is None:
            raise HTTPException(404, detail="No 1-stop strategies to plot")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return _cached_png_response(key, buf)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, detail=f"Undercut plot failed: {e}")


@app.post("/api/rival/compare-plot")
def rival_compare_plot(body: dict):
    """Render a side-by-side comparison plot (Undercut vs Overcut) from
    precomputed scan arrays. Expects `undercut_scan` and `overcut_scan` as
    lists of timeline dicts (lap, mean_ev, p10_ev, p50_ev, p90_ev, win_rate, recommend).
    """
    try:
        u_scan = body.get("undercut_scan") or body.get("undercut_timeline")
        o_scan = body.get("overcut_scan") or body.get("overcut_timeline")
        if not u_scan or not o_scan:
            raise HTTPException(400, detail="Both undercut_scan and overcut_scan required")

        # cache key
        key = _make_key({"type": "compare", "u": u_scan, "o": o_scan, "rival": body.get("rival"), "driver": body.get("driver")})
        p = PLOT_CACHE / f"{key}.png"
        if p.exists():
            return StreamingResponse(p.open("rb"), media_type="image/png")

        u_df = pd.DataFrame(u_scan)
        o_df = pd.DataFrame(o_scan)

        fig = plot_undercut_vs_overcut(u_df, o_df, rival_driver=body.get("rival", "RIVAL"), our_driver=body.get("driver", "US"), save=False)
        if fig is None:
            raise HTTPException(404, detail="Failed to generate comparison plot")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return _cached_png_response(key, buf)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, detail=f"Compare plot failed: {e}")


@app.post("/api/overcut/plot")
def overcut_plot(body: dict):
    """Generate an Overcut EV timeline plot as PNG.

    Accepts either a precomputed `overcut_scan` list (timeline dicts) or
    will compute via `scan_overcut_window` when provided session inputs.
    """
    try:
        over_scan = body.get("overcut_scan") or body.get("overcut_timeline")
        rival_driver = body.get("rival", "RIVAL")
        our_driver = body.get("driver", "US")

        if over_scan:
            o_df = pd.DataFrame(over_scan)
            key = _make_key({"type": "overcut", "o": over_scan, "rival": rival_driver, "driver": our_driver})
            p = PLOT_CACHE / f"{key}.png"
            if p.exists():
                return StreamingResponse(p.open("rb"), media_type="image/png")
        else:
            # fallback to computing scan (legacy behaviour)
            year = int(body.get("year", 0))
            race = body.get("race")
            driver = body.get("driver", "VER")
            n_simulations = int(body.get("n_simulations", 200))
            noise_std = float(body.get("noise_std", 0.3))

            session = _get_cached_session(year, race)
            laps_raw = get_laps(session)
            pit_stops = get_pit_stops(session)
            race_laps = get_race_laps(session) or 57

            cleaned = clean_laps(laps_raw)
            laps = engineer_features(cleaned, total_laps=race_laps)
            deg_model = TyreDegModel()
            deg_model.fit(laps, driver=driver)
            weather = get_track_temp(session)
            if weather:
                deg_model.set_track_temp(float(weather.get("track_temp")))

            pit_loss = get_pit_loss(pit_stops)

            our_row = next((r for r in get_timing_tower_data(session) if r.get("driver") == driver), None)
            riv_row = next((r for r in get_timing_tower_data(session) if r.get("driver") == body.get("rival")), None)
            our_compound_raw = (our_row or {}).get("compound") or "MEDIUM"
            our_age = int((our_row or {}).get("tyre_age") or 8)
            riv_compound_raw = (riv_row or {}).get("compound") or "MEDIUM"
            riv_age = int((riv_row or {}).get("tyre_age") or 10)
            our_gap = (our_row or {}).get("gap")
            riv_gap = (riv_row or {}).get("gap")
            gap_to_us = (
                float(riv_gap) - float(our_gap)
                if our_gap is not None and riv_gap is not None else 2.5
            )
            # Same fitted-compound guard as /api/simulate — see
            # _pick_fitted_compound/_pick_switch_compound docstrings.
            our_compound = _pick_fitted_compound(deg_model, our_compound_raw)
            riv_compound = _pick_fitted_compound(deg_model, riv_compound_raw) or our_compound
            if our_compound is None:
                raise HTTPException(422, detail="No fitted tyre compounds for this driver/session.")
            new_compound = _pick_switch_compound(deg_model, our_compound, body.get("new_compound"))
            if new_compound is None:
                raise HTTPException(
                    422,
                    detail=f"Not enough compound diversity to model a switch "
                            f"(driver ran: {sorted(deg_model.models.keys())}).",
                )
            rival_state = RivalState(
                driver=body.get("rival", "RIVAL"),
                compound=str(riv_compound).upper(),
                tyre_age=max(1, riv_age),
                gap_to_us=gap_to_us,
            )
            from_lap = max(8, (race_laps // 4))
            to_lap = min(race_laps - 8, race_laps // 2 + 5)
            over_df = scan_overcut_window(
                from_lap=from_lap, to_lap=to_lap,
                our_compound=str(our_compound).upper(),
                our_tyre_age_at_from_lap=max(1, our_age),
                new_compound=new_compound,
                rival=rival_state, deg_model=deg_model, pit_loss=pit_loss,
                n_simulations=min(150, n_simulations), noise_std=noise_std,
            )
            o_df = over_df

            # cache key for computed overcut
            key = _make_key({
                "type": "overcut", "year": year, "race": race, "driver": driver,
                "n_simulations": n_simulations, "noise_std": noise_std,
            })
            p = PLOT_CACHE / f"{key}.png"
            if p.exists():
                return StreamingResponse(p.open("rb"), media_type="image/png")

        if o_df is None or o_df.empty:
            raise HTTPException(404, detail="No overcut data to plot")

        fig = plot_undercut_ev_timeline(o_df, rival_driver, our_driver, mode_label="OVERCUT", save=False)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return _cached_png_response(key, buf)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, detail=f"Overcut plot failed: {e}")


@app.post("/api/backtest/plot")
def backtest_plot(body: dict):
    """Render lap-trace for backtest actual vs optimal as PNG.

    Expects `backtest` payload as returned by `/api/simulate` under key `backtest`,
    or `actual` and `optimal` dicts with `lap_times` and `pit_laps`.
    """
    try:
        bt = body.get("backtest") or {}
        actual = bt.get("actual") or body.get("actual")
        optimal = bt.get("optimal") or body.get("optimal")
        if not actual or not optimal:
            raise HTTPException(400, detail="Backtest requires actual and optimal results")

        # build series
        strategies = [actual, optimal]
        labels = [actual.get("label", "Actual"), optimal.get("label", "AI Optimal")]

        # cache key
        key = _make_key({"type": "backtest", "a": actual, "o": optimal})
        p = PLOT_CACHE / f"{key}.png"
        if p.exists():
            return StreamingResponse(p.open("rb"), media_type="image/png")

        fig = plot_lap_trace(strategies, labels=labels, save=False)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return _cached_png_response(key, buf)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, detail=f"Backtest plot failed: {e}")



class RivalAnalysisRequest(BaseModel):
    year: int
    race: str
    driver: str = "VER"
    rival: str = "NOR"
    rival_compound: str = "MEDIUM"
    rival_tyre_age: int = Field(default=10, ge=1, le=40)
    gap_to_rival: float = 2.0
    scan_from_lap: int = Field(default=15, ge=1)
    scan_to_lap: int = Field(default=30, ge=2)
    our_compound: str = "MEDIUM"
    our_tyre_age: int = Field(default=10, ge=1, le=40)
    new_compound: str = "HARD"
    n_simulations: int = Field(default=200, ge=50, le=1000)
    noise_std: float = 0.3
    run_h2h: bool = True


@app.post("/api/rival-analysis")
def rival_analysis(req: RivalAnalysisRequest) -> dict[str, Any]:
    """Interactive rival scan + optional head-to-head MC (full dashboard Tab 5)."""
    # Same split as /api/simulate: upstream data-load failures are 502,
    # genuine bugs in the analysis logic below are 500.
    try:
        session = _get_cached_session(req.year, req.race)
        laps_raw = get_laps(session)
        pit_stops = get_pit_stops(session)
        race_laps = get_race_laps(session) or 57
        weather = get_track_temp(session)
    except Exception as e:
        raise HTTPException(502, detail=f"Failed to load session {req.year} {req.race}: {e}")

    try:
        track_temp = weather.get("track_temp") if weather else None

        cleaned = clean_laps(laps_raw)
        laps = engineer_features(cleaned, total_laps=race_laps)
        deg_model = TyreDegModel()
        deg_model.fit(laps, driver=req.driver)
        if track_temp is not None:
            deg_model.set_track_temp(float(track_temp))
        pit_loss = get_pit_loss(pit_stops)

        # our_compound/new_compound are explicit user choices here (unlike
        # /api/simulate's auto-inferred rival block) — silently substituting
        # a different compound behind the user's back would be confusing.
        # Validate up front and report exactly what's available instead.
        fitted = sorted(deg_model.models.keys())
        requested = {req.our_compound.upper(), req.new_compound.upper()}
        missing = requested - set(fitted)
        if missing:
            raise HTTPException(
                422,
                detail=(
                    f"{req.driver} has no fitted tyre model for: {sorted(missing)}. "
                    f"Compounds available this session: {fitted}."
                ),
            )

        from_lap = max(1, min(req.scan_from_lap, race_laps - 5))
        to_lap = max(from_lap + 1, min(req.scan_to_lap, race_laps - 2))

        rival_state = RivalState(
            driver=req.rival,
            compound=req.rival_compound.upper(),
            tyre_age=req.rival_tyre_age,
            gap_to_us=req.gap_to_rival,
        )
        under_df = scan_undercut_window(
            from_lap=from_lap, to_lap=to_lap,
            our_compound=req.our_compound.upper(),
            our_tyre_age_at_from_lap=req.our_tyre_age,
            new_compound=req.new_compound.upper(),
            rival=rival_state, deg_model=deg_model, pit_loss=pit_loss,
            n_simulations=req.n_simulations, noise_std=req.noise_std,
        )
        over_df = scan_overcut_window(
            from_lap=from_lap, to_lap=to_lap,
            our_compound=req.our_compound.upper(),
            our_tyre_age_at_from_lap=req.our_tyre_age,
            new_compound=req.new_compound.upper(),
            rival=rival_state, deg_model=deg_model, pit_loss=pit_loss,
            n_simulations=req.n_simulations, noise_std=req.noise_std,
        )
        under_list = _scan_to_list(under_df)
        over_list = _scan_to_list(over_df)
        rec_u = [r for r in under_list if r["recommend"]]
        rec_o = [r for r in over_list if r["recommend"]]
        best_u = max(rec_u, key=lambda r: r["mean_ev"]) if rec_u else (max(under_list, key=lambda r: r["mean_ev"]) if under_list else None)
        best_o = max(rec_o, key=lambda r: r["mean_ev"]) if rec_o else (max(over_list, key=lambda r: r["mean_ev"]) if over_list else None)

        recommendation = None
        if best_u or best_o:
            u_ev = best_u["mean_ev"] if best_u else -999
            o_ev = best_o["mean_ev"] if best_o else -999
            if u_ev > -999 or o_ev > -999:
                winner = "UNDERCUT" if u_ev >= o_ev else "OVERCUT"
                recommendation = {
                    "winner": winner,
                    "best_ev": max(u_ev, o_ev),
                    "undercut_favourable_laps": len(rec_u),
                    "overcut_favourable_laps": len(rec_o),
                }

        h2h_rows = []
        if req.run_h2h:
            try:
                cand = generate_one_stop_strategies(race_laps)[:20]
                rival_remaining = race_laps - from_lap
                rival_on_current = min(rival_remaining, max(5, rival_remaining // 2))
                if rival_remaining > 10:
                    # Same fitted-compound guard as elsewhere — deg_model
                    # was fit for req.driver, used here as a pace proxy for
                    # the rival's continuation strategy, so it must only
                    # reference compounds that driver actually ran.
                    alt = _pick_switch_compound(deg_model, req.rival_compound.upper()) \
                        or req.rival_compound.upper()
                    rival_strat = Strategy(stints=[
                        Stint(req.rival_compound.upper(), rival_on_current),
                        Stint(alt, max(1, rival_remaining - rival_on_current)),
                    ])
                else:
                    pool = generate_one_stop_strategies(race_laps)
                    rival_strat = pool[0] if pool else cand[0]
                h2h = run_rival_monte_carlo(
                    our_strategies=cand,
                    rival_strategy=rival_strat,
                    deg_model=deg_model,
                    pit_loss=pit_loss,
                    initial_gap=req.gap_to_rival,
                    n_simulations=min(150, req.n_simulations),
                    noise_std=req.noise_std,
                )
                for _, row in h2h.head(15).iterrows():
                    h2h_rows.append({
                        "strategy": str(row.get("strategy", "")),
                        "win_rate": float(row["win_rate"]) if row.get("win_rate") is not None else None,
                        "mean_final_gap": float(row["mean_final_gap"]) if row.get("mean_final_gap") is not None else None,
                    })
            except Exception:
                traceback.print_exc()

        race_trace = None
        try:
            # Simulate the window's remaining distance. Our car pits at its
            # start; the rival continues for half the remaining race.
            remaining = race_laps - from_lap
            rival_stay = max(1, remaining // 2)
            rival_next = _pick_switch_compound(deg_model, req.rival_compound.upper())
            our_strategy = Strategy([Stint(req.new_compound.upper(), remaining)])
            rival_strategy = Strategy([
                Stint(req.rival_compound.upper(), rival_stay),
                Stint(rival_next or req.new_compound.upper(), remaining - rival_stay),
            ])
            race_trace = simulate_race_with_rival(
                our_strategy, rival_strategy, deg_model, pit_loss,
                initial_gap=req.gap_to_rival + pit_loss,
            )
            # Initial stop happens immediately, before the first remaining lap.
            race_trace["our_pit_laps"] = [from_lap]
            race_trace["rival_pit_laps"] = [from_lap + p for p in race_trace["rival_pit_laps"]]
        except Exception:
            traceback.print_exc()

        return {
            "rival": req.rival,
            "driver": req.driver,
            "undercut_timeline": under_list,
            "overcut_timeline": over_list,
            "best_undercut": best_u,
            "best_overcut": best_o,
            "recommendation": recommendation,
            "h2h": h2h_rows,
            "race_trace": race_trace,
            "scan_from_lap": from_lap,
            "scan_to_lap": to_lap,
            "pit_loss": pit_loss,
            "race_laps": race_laps,
        }
    except HTTPException:
        # Without this, the bare `except Exception` below would catch our
        # own intentional HTTPException(422, ...) raised above (it IS an
        # Exception subclass) and re-wrap it as a generic 500 — turning a
        # clear, actionable "MEDIUM isn't fitted for this driver" message
        # into an opaque server-error page. Every other endpoint in this
        # file already guards against this; this one was missing it.
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, detail=f"Rival analysis failed: {e}")


# Register static files after API routes, preserving a single browser origin.
if (ROOT / "frontend/dist").is_dir():
    app.mount("/", StaticFiles(directory=ROOT / "frontend/dist", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

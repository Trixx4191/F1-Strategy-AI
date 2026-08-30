"""
dashboard_mc.py — F1 Strategy AI · Mission Control Edition

Multi-panel race-engineer workstation.
Uses the existing simulation pipeline; presentation is fully componentised
so panels can later be ported to a more flexible frontend.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from src.pipeline.loader import (
    load_session, get_laps, get_pit_stops,
    get_race_schedule, get_session_drivers, get_race_laps,
    get_track_temp, get_final_classification, get_latest_available_year,
    get_timing_tower_data, get_circuit_outline,
)
from src.pipeline.cleaner import clean_laps
from src.pipeline.features import engineer_features
from src.models.tyre_deg import TyreDegModel
from src.models.pit_loss import get_pit_loss
from src.simulator.strategy import (
    generate_one_stop_strategies, generate_two_stop_strategies,
)
from src.simulator.monte_carlo import run_monte_carlo
from src.simulator.rival import RivalState, scan_undercut_window, scan_overcut_window
from src.utils.config import COMPOUNDS, N_SIMULATIONS

from src.visualisation.components.theme import inject_theme
from src.visualisation.components.top_bar import render_top_bar
from src.visualisation.components.timing_tower import render_timing_tower
from src.visualisation.components.track_map import render_track_map
from src.visualisation.components.driver_cards import render_driver_cards
from src.visualisation.components.strategy_panel import render_strategy_panel
from src.visualisation.components.sim_progress import render_sim_progress
from src.visualisation.components.rival_panel import render_rival_panel
from src.visualisation.components.tyre_strip import render_tyre_strip

# ── Static driver metadata (extend as needed for 2025/2026 grids) ────────────
DRIVERS = {
    "VER": {"name": "VERSTAPPEN", "first": "Max", "team": "RED BULL", "color": "#3671C6", "num": "1"},
    "PER": {"name": "PÉREZ", "first": "Sergio", "team": "RED BULL", "color": "#3671C6", "num": "11"},
    "LEC": {"name": "LECLERC", "first": "Charles", "team": "FERRARI", "color": "#E8002D", "num": "16"},
    "SAI": {"name": "SAINZ", "first": "Carlos", "team": "FERRARI", "color": "#E8002D", "num": "55"},
    "HAM": {"name": "HAMILTON", "first": "Lewis", "team": "MERCEDES", "color": "#00D2BE", "num": "44"},
    "RUS": {"name": "RUSSELL", "first": "George", "team": "MERCEDES", "color": "#00D2BE", "num": "63"},
    "NOR": {"name": "NORRIS", "first": "Lando", "team": "MCLAREN", "color": "#FF8000", "num": "4"},
    "PIA": {"name": "PIASTRI", "first": "Oscar", "team": "MCLAREN", "color": "#FF8000", "num": "81"},
    "ALO": {"name": "ALONSO", "first": "Fernando", "team": "ASTON MARTIN", "color": "#229971", "num": "14"},
    "STR": {"name": "STROLL", "first": "Lance", "team": "ASTON MARTIN", "color": "#229971", "num": "18"},
    "GAS": {"name": "GASLY", "first": "Pierre", "team": "ALPINE", "color": "#0093CC", "num": "10"},
    "OCO": {"name": "OCON", "first": "Esteban", "team": "ALPINE", "color": "#0093CC", "num": "31"},
    "ALB": {"name": "ALBON", "first": "Alexander", "team": "WILLIAMS", "color": "#005AFF", "num": "23"},
    "SAR": {"name": "SARGEANT", "first": "Logan", "team": "WILLIAMS", "color": "#005AFF", "num": "2"},
    "BOT": {"name": "BOTTAS", "first": "Valtteri", "team": "KICK SAUBER", "color": "#52E252", "num": "77"},
    "ZHO": {"name": "ZHOU", "first": "Guanyu", "team": "KICK SAUBER", "color": "#52E252", "num": "24"},
    "HUL": {"name": "HÜLKENBERG", "first": "Nico", "team": "HAAS", "color": "#B6BABD", "num": "27"},
    "MAG": {"name": "MAGNUSSEN", "first": "Kevin", "team": "HAAS", "color": "#B6BABD", "num": "20"},
    "TSU": {"name": "TSUNODA", "first": "Yuki", "team": "RB", "color": "#6692FF", "num": "22"},
    "RIC": {"name": "RICCIARDO", "first": "Daniel", "team": "RB", "color": "#6692FF", "num": "3"},
}

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="F1 STRATEGY AI · Mission Control",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()

# ── Sidebar (control surface) ────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        """
        <div style="padding:1.1rem 1.1rem 0.8rem;border-bottom:1px solid #1e1e1e">
          <div style="font-family:'Antonio',sans-serif;font-size:0.55rem;letter-spacing:0.3em;color:#555">MISSION CONTROL</div>
          <div style="font-family:'Antonio',sans-serif;font-size:1.25rem;font-weight:700;letter-spacing:0.04em;color:#f5f5f5">
            F1 <span style="color:#e8002d">STRATEGY</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div style="padding:0.7rem 1.1rem 0.2rem;font-size:0.55rem;letter-spacing:0.22em;color:#333;text-transform:uppercase">Session</div>', unsafe_allow_html=True)

    @st.cache_data(show_spinner=False, ttl=86400)
    def _get_latest_year():
        return get_latest_available_year()

    latest_year = _get_latest_year()
    year_options = list(range(latest_year, 2017, -1))
    year = st.selectbox("SEASON", year_options, index=0, label_visibility="collapsed")

    @st.cache_data(show_spinner=False)
    def _get_races(y):
        return get_race_schedule(y, only_completed=(y == latest_year))

    race_list = _get_races(year)
    if not race_list:
        st.warning(f"No completed races found yet for {year}.")
        st.stop()
    race = st.selectbox("GRAND PRIX", race_list, index=0, label_visibility="collapsed")

    st.markdown('<div style="padding:0.7rem 1.1rem 0.2rem;font-size:0.55rem;letter-spacing:0.22em;color:#333;text-transform:uppercase">Driver</div>', unsafe_allow_html=True)
    driver_code = st.selectbox("SELECT DRIVER", list(DRIVERS.keys()), index=0, label_visibility="collapsed")

    st.markdown('<div style="padding:0.7rem 1.1rem 0.2rem;font-size:0.55rem;letter-spacing:0.22em;color:#333;text-transform:uppercase">Rival</div>', unsafe_allow_html=True)
    rival_options = [c for c in DRIVERS.keys() if c != driver_code]
    rival_code = st.selectbox("RIVAL DRIVER", rival_options, index=min(1, len(rival_options)-1) if rival_options else 0, label_visibility="collapsed")

    st.markdown('<div style="padding:0.7rem 1.1rem 0.2rem;font-size:0.55rem;letter-spacing:0.22em;color:#333;text-transform:uppercase">Simulation</div>', unsafe_allow_html=True)
    n_sims = st.slider("MC ITERATIONS", 100, 2000, N_SIMULATIONS, step=100)
    stop_strategy = st.radio("STRATEGY TYPE", ["1-stop", "2-stop", "Both"], horizontal=True)
    noise = st.slider("LAP TIME NOISE (s)", 0.0, 1.0, 0.3, step=0.05)

    use_live_temp = st.checkbox("Use live session temperature", value=True)
    manual_temp = None
    if not use_live_temp:
        manual_temp = st.slider("Track temp override (°C)", 15, 55, 35)

    st.markdown("<br>", unsafe_allow_html=True)
    run_btn = st.button("▶  RUN SIMULATION", use_container_width=True, type="primary")

# ── Session state defaults ───────────────────────────────────────────────────
if "mc_status" not in st.session_state:
    st.session_state.mc_status = "idle"
if "mc_results" not in st.session_state:
    st.session_state.mc_results = None

# ── Run simulation when requested ────────────────────────────────────────────
if run_btn:
    st.session_state.mc_status = "loading"
    st.session_state.mc_results = None
    st.rerun()

results = st.session_state.mc_results

if st.session_state.mc_status in ("loading", "simulating") and results is None:
    with st.spinner("Loading session & running Monte Carlo…"):
        try:
            session = load_session(year, race)
            laps_raw = get_laps(session)
            pit_stops = get_pit_stops(session)
            weather = get_track_temp(session) if use_live_temp else None
            if weather and isinstance(weather, dict):
                track_temp = weather.get("track_temp")
            elif manual_temp is not None:
                track_temp = manual_temp
            else:
                track_temp = None

            laps = engineer_features(clean_laps(laps_raw))
            deg_model = TyreDegModel()
            deg_model.fit(laps, driver=driver_code)
            if track_temp is not None:
                deg_model.set_track_temp(track_temp)

            pit_loss = get_pit_loss(pit_stops)
            race_laps = get_race_laps(session) or 57

            # Real circuit geometry from FastF1 (session.get_circuit_info()) —
            # not a hardcoded shape. render_track_map() shows an honest
            # "no geometry available" state when FastF1 doesn't have corner
            # data for this session, rather than a schematic stand-in.
            circuit = get_circuit_outline(session)

            strategies = []
            if stop_strategy in ("1-stop", "Both"):
                strategies.extend(generate_one_stop_strategies(total_laps=race_laps))
            if stop_strategy in ("2-stop", "Both"):
                strategies.extend(generate_two_stop_strategies(total_laps=race_laps))

            if not strategies:
                raise RuntimeError("No strategies generated — check race lap count.")

            mc_df = run_monte_carlo(
                strategies,
                deg_model,
                pit_loss=pit_loss,
                n_simulations=n_sims,
                noise_std=noise,
            )

            # Dense timing tower from classification + last stint data
            timing_rows = get_timing_tower_data(session)
            for row in timing_rows:
                meta = DRIVERS.get(row["driver"], {})
                row["team_color"] = meta.get("color", "#888")
                if not row.get("name") or row["name"] == row["driver"]:
                    row["name"] = meta.get("name", row["driver"])

            # Tyre cliff summary
            tyre_summary = []
            for c in COMPOUNDS:
                try:
                    cliff = deg_model.cliff_lap(c)
                    ci = deg_model.cliff_ci(c)
                    tyre_summary.append({
                        "compound": c,
                        "cliff_lap": cliff,
                        "cliff_ci_low": ci[0] if ci else None,
                        "cliff_ci_high": ci[1] if ci else None,
                        "n_laps": None,
                    })
                except Exception:
                    pass

            # Strategy results for panel
            strat_rows = []
            if mc_df is not None and not mc_df.empty:
                sorted_mc = mc_df.sort_values("mean_time").head(8)
                for rank, (_, r) in enumerate(sorted_mc.iterrows(), 1):
                    compounds = r.get("compounds")
                    if not compounds and hasattr(r.get("strategy_obj"), "stints"):
                        compounds = [s.compound for s in r["strategy_obj"].stints]
                    if isinstance(compounds, str):
                        compounds = [c.strip() for c in compounds.replace("→", ",").split(",") if c.strip()]
                    pit_laps = []
                    obj = r.get("strategy_obj")
                    if obj is not None and hasattr(obj, "stints") and len(obj.stints) > 1:
                        cumulative = 0
                        for stint in obj.stints[:-1]:
                            cumulative += stint.duration
                            pit_laps.append(cumulative)
                    strat_rows.append({
                        "rank": rank,
                        "compound_sequence": compounds or [],
                        "pit_laps": pit_laps,
                        "mean_time": r.get("mean_time"),
                        "p10": r.get("p10"),
                        "p50": r.get("p50"),
                        "p90": r.get("p90"),
                    })


            # ── Rival undercut / overcut scan ─────────────────────────────
            rival_result = {
                "rival_code": rival_code,
                "undercut_best_ev": None,
                "undercut_best_lap": None,
                "overcut_best_ev": None,
                "overcut_best_lap": None,
                "win_rate_under": None,
                "win_rate_over": None,
                "recommended_window": None,
            }
            try:
                # Build rival state from timing data when available
                our_row = next((r for r in timing_rows if r.get("driver") == driver_code), None)
                riv_row = next((r for r in timing_rows if r.get("driver") == rival_code), None)

                our_compound = (our_row or {}).get("compound") or "MEDIUM"
                our_age = int((our_row or {}).get("tyre_age") or 8)
                riv_compound = (riv_row or {}).get("compound") or "MEDIUM"
                riv_age = int((riv_row or {}).get("tyre_age") or 10)

                # Gap: positive = rival ahead of us
                our_gap = (our_row or {}).get("gap")
                riv_gap = (riv_row or {}).get("gap")
                if our_gap is not None and riv_gap is not None:
                    gap_to_us = float(riv_gap) - float(our_gap)  # rival relative to us
                else:
                    gap_to_us = 2.5  # default small gap ahead

                rival_state = RivalState(
                    driver=rival_code,
                    compound=riv_compound.upper() if riv_compound else "MEDIUM",
                    tyre_age=max(1, riv_age),
                    gap_to_us=gap_to_us,
                )

                # Scan a mid-race window
                from_lap = max(8, race_laps // 4)
                to_lap = min(race_laps - 8, race_laps // 2 + 5)
                new_compound = "SOFT" if our_compound.upper() != "SOFT" else "MEDIUM"

                under_df = scan_undercut_window(
                    from_lap=from_lap,
                    to_lap=to_lap,
                    our_compound=our_compound.upper(),
                    our_tyre_age_at_from_lap=max(1, our_age),
                    new_compound=new_compound,
                    rival=rival_state,
                    deg_model=deg_model,
                    pit_loss=pit_loss,
                    n_simulations=min(200, n_sims),
                    noise_std=noise,
                )
                over_df = scan_overcut_window(
                    from_lap=from_lap,
                    to_lap=to_lap,
                    our_compound=our_compound.upper(),
                    our_tyre_age_at_from_lap=max(1, our_age),
                    new_compound=new_compound,
                    rival=rival_state,
                    deg_model=deg_model,
                    pit_loss=pit_loss,
                    n_simulations=min(200, n_sims),
                    noise_std=noise,
                )

                if under_df is not None and not under_df.empty:
                    best_u = under_df.loc[under_df["mean_ev"].idxmax()]
                    rival_result["undercut_best_ev"] = float(best_u["mean_ev"])
                    rival_result["undercut_best_lap"] = int(best_u["lap"])
                    rival_result["win_rate_under"] = float(best_u["win_rate"])
                    rec = under_df[under_df["recommend"] == True]
                    if not rec.empty:
                        rival_result["recommended_window"] = (
                            int(rec["lap"].min()), int(rec["lap"].max())
                        )

                if over_df is not None and not over_df.empty:
                    best_o = over_df.loc[over_df["mean_ev"].idxmax()]
                    rival_result["overcut_best_ev"] = float(best_o["mean_ev"])
                    rival_result["overcut_best_lap"] = int(best_o["lap"])
                    rival_result["win_rate_over"] = float(best_o["win_rate"])
            except Exception as riv_err:
                # Non-fatal — panel shows placeholders
                import traceback
                traceback.print_exc()


            # Map nodes from timing (selected driver highlighted)
            map_nodes = []
            for row in timing_rows[:12]:
                map_nodes.append({
                    "code": row["driver"],
                    "compound": row.get("compound"),
                    "color": row.get("team_color", "#888"),
                    "selected": row["driver"] == driver_code,
                })

            weather_summary = "—"
            if weather and isinstance(weather, dict):
                parts = []
                if weather.get("track_temp") is not None:
                    parts.append(f"TRK {weather['track_temp']:.0f}°C")
                if weather.get("air_temp") is not None:
                    parts.append(f"AIR {weather['air_temp']:.0f}°C")
                if weather.get("rainfall"):
                    parts.append("RAIN")
                weather_summary = " · ".join(parts) if parts else "—"

            st.session_state.mc_results = {
                "timing_rows": timing_rows,
                "tyre_summary": tyre_summary,
                "strat_rows": strat_rows,
                "track_temp": track_temp,
                "weather_summary": weather_summary,
                "map_nodes": map_nodes,
                "race_laps": race_laps,
                "n_sims": n_sims,
                "driver": driver_code,
                "race": race,
                "rival": rival_result,
                "circuit": circuit,
            }
            st.session_state.mc_status = "ready"
            st.rerun()
        except Exception as e:
            import traceback
            st.session_state.mc_status = "idle"
            st.session_state.mc_results = None
            st.error(f"Simulation failed ({year} {race}): {e}")
            with st.expander("Error details"):
                st.code(traceback.format_exc())
            st.info("Try another completed race, or check FastF1 has data for this event.")
            st.stop()

# ── Multi-panel shell ────────────────────────────────────────────────────────
res = st.session_state.mc_results or {}
timing_rows = res.get("timing_rows") or []
tyre_summary = res.get("tyre_summary") or []
strat_rows = res.get("strat_rows") or []
map_nodes = res.get("map_nodes") or []
race_laps = res.get("race_laps") or 0
n_sims_done = res.get("n_sims") or 0
weather_summary = res.get("weather_summary") or "—"
track_temp_display = res.get("track_temp")
circuit = res.get("circuit") or {}

st.markdown(
    render_top_bar(
        year=year,
        race=race,
        driver=driver_code,
        status=st.session_state.mc_status,
        track_temp=track_temp_display,
        weather_summary=weather_summary,
    ),
    unsafe_allow_html=True,
)

# Driver cards from timing data (selected first, then next few)
meta = DRIVERS.get(driver_code, {})
driver_nodes = []
selected_row = next((r for r in timing_rows if r.get("driver") == driver_code), None)
cliff_default = next((t["cliff_lap"] for t in tyre_summary if t.get("cliff_lap")), None)
if selected_row:
    driver_nodes.append({
        "code": driver_code,
        "team": selected_row.get("team") or meta.get("team", ""),
        "color": selected_row.get("team_color") or meta.get("color", "#888"),
        "compound": selected_row.get("compound") or "—",
        "tyre_age": selected_row.get("tyre_age"),
        "cliff_lap": cliff_default,
        "gap_to_rival": selected_row.get("gap"),
        "phase": "plateau" if st.session_state.mc_status == "ready" else "—",
    })
else:
    driver_nodes.append({
        "code": driver_code,
        "team": meta.get("team", ""),
        "color": meta.get("color", "#888"),
        "compound": "—",
        "tyre_age": None,
        "cliff_lap": cliff_default,
        "gap_to_rival": None,
        "phase": "—",
    })
for r in timing_rows:
    if r.get("driver") == driver_code:
        continue
    if len(driver_nodes) >= 4:
        break
    m = DRIVERS.get(r["driver"], {})
    driver_nodes.append({
        "code": r["driver"],
        "team": r.get("team") or m.get("team", ""),
        "color": r.get("team_color") or m.get("color", "#888"),
        "compound": r.get("compound") or "—",
        "tyre_age": r.get("tyre_age"),
        "cliff_lap": None,
        "gap_to_rival": r.get("gap"),
        "phase": "—",
    })

# Row 1: Timing | Track | Driver cards
c1, c2, c3 = st.columns([1.1, 1.4, 0.9], gap="small")
with c1:
    st.markdown(
        render_timing_tower(timing_rows, selected_driver=driver_code),
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        render_track_map(race_name=race, nodes=map_nodes or None, circuit=circuit),
        unsafe_allow_html=True,
    )
with c3:
    st.markdown(
        render_driver_cards(driver_nodes, selected_code=driver_code),
        unsafe_allow_html=True,
    )

# Row 2: Strategy | Sim progress | Rival
c4, c5, c6 = st.columns([1.1, 1.2, 1.0], gap="small")
rival_data = res.get("rival") or {}
rec_window = rival_data.get("recommended_window")

with c4:
    st.markdown(
        render_strategy_panel(strat_rows, recommended_window=rec_window),
        unsafe_allow_html=True,
    )
with c5:
    st.markdown(
        render_sim_progress(
            current_lap=race_laps if st.session_state.mc_status == "ready" else 0,
            total_laps=race_laps,
            stint_phase="plateau" if st.session_state.mc_status == "ready" else "—",
            mc_done=n_sims_done if st.session_state.mc_status == "ready" else 0,
            mc_total=n_sims_done or n_sims,
            recommended_window=rec_window,
        ),
        unsafe_allow_html=True,
    )
with c6:
    st.markdown(
        render_rival_panel(
            rival_code=rival_data.get("rival_code") or rival_code,
            undercut_best_ev=rival_data.get("undercut_best_ev"),
            undercut_best_lap=rival_data.get("undercut_best_lap"),
            overcut_best_ev=rival_data.get("overcut_best_ev"),
            overcut_best_lap=rival_data.get("overcut_best_lap"),
            win_rate_under=rival_data.get("win_rate_under"),
            win_rate_over=rival_data.get("win_rate_over"),
        ),
        unsafe_allow_html=True,
    )

# Bottom strip
st.markdown(
    render_tyre_strip(tyre_summary),
    unsafe_allow_html=True,
)

# Footer note
st.markdown(
    """
    <div style="margin-top:0.8rem;font-size:0.58rem;letter-spacing:0.12em;color:#333;text-transform:uppercase">
      Mission Control · Phase B2 · Timing tower · Track map · Rival undercut/overcut EV · Strategy MC
    </div>
    """,
    unsafe_allow_html=True,
)

"""
RETIRED — this was the original F1 Strategy AI Streamlit dashboard, built
before the FastAPI + React stack existed. Retired after a full tab-by-tab
feature-parity audit against the React frontend confirmed every feature
had a confirmed match or was exceeded — see docs/decisions.md for the
audit writeup and docs/frontend_react.md for the parity table. Kept here
for reference/history only; do not run in production or extend further.
The React + FastAPI stack (backend/main.py + frontend/) is the primary
interface going forward. src/visualisation/dashboard_mc.py remains as a
lightweight, no-build-step local option.
"""

"""
dashboard.py — F1 Strategy AI · Terminal Edition (v2)

Design language: broadcast-dark data terminal.
  - Photos kept, elevated with a layered glass-noise overlay
  - Animated feature cards on landing
  - Fully functional tabs with live-data cliff badges, backtest, rival H2H
  - Every button / menu does exactly what it says
"""

import sys, base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.pyplot as plt

from src.pipeline.loader import (
    load_session, get_laps, get_pit_stops,
    get_race_schedule, get_session_drivers, get_race_laps,
    get_track_temp, get_final_classification, get_latest_available_year,
)
from src.pipeline.cleaner import clean_laps
from src.pipeline.features import engineer_features
from src.models.tyre_deg import TyreDegModel
from src.models.pit_loss import get_pit_loss
from src.simulator.strategy import (
    generate_one_stop_strategies, generate_two_stop_strategies, Strategy, Stint,
)
from src.simulator.monte_carlo import run_monte_carlo, run_rival_monte_carlo
from src.simulator.race_sim import simulate_race
from src.visualisation.tyre_plots import (
    plot_degradation_curves, plot_stint_scatter, plot_compound_comparison_table,
)
from src.visualisation.strategy_plots import (
    plot_strategy_comparison, plot_lap_trace, plot_undercut_window,
)
from src.simulator.rival import RivalState, scan_undercut_window, scan_overcut_window
from src.visualisation.rival_plots import (
    plot_undercut_ev_timeline, plot_gap_trace, plot_head_to_head_mc,
    plot_undercut_vs_overcut,
)
from src.utils.config import COMPOUNDS, RACE_LAPS, N_SIMULATIONS

# ── Static data ───────────────────────────────────────────────────────────────
DRIVERS = {
    "VER": {"name":"VERSTAPPEN", "first":"Max",       "team":"RED BULL RACING",  "color":"#3671C6","num":"1"},
    "PER": {"name":"PÉREZ",      "first":"Sergio",    "team":"RED BULL RACING",  "color":"#3671C6","num":"11"},
    "LEC": {"name":"LECLERC",    "first":"Charles",   "team":"FERRARI",          "color":"#E8002D","num":"16"},
    "SAI": {"name":"SAINZ",      "first":"Carlos",    "team":"FERRARI",          "color":"#E8002D","num":"55"},
    "HAM": {"name":"HAMILTON",   "first":"Lewis",     "team":"MERCEDES",         "color":"#00D2BE","num":"44"},
    "RUS": {"name":"RUSSELL",    "first":"George",    "team":"MERCEDES",         "color":"#00D2BE","num":"63"},
    "NOR": {"name":"NORRIS",     "first":"Lando",     "team":"MCLAREN",          "color":"#FF8000","num":"4"},
    "PIA": {"name":"PIASTRI",    "first":"Oscar",     "team":"MCLAREN",          "color":"#FF8000","num":"81"},
    "ALO": {"name":"ALONSO",     "first":"Fernando",  "team":"ASTON MARTIN",     "color":"#229971","num":"14"},
    "STR": {"name":"STROLL",     "first":"Lance",     "team":"ASTON MARTIN",     "color":"#229971","num":"18"},
    "GAS": {"name":"GASLY",      "first":"Pierre",    "team":"ALPINE",           "color":"#0093CC","num":"10"},
    "OCO": {"name":"OCON",       "first":"Esteban",   "team":"ALPINE",           "color":"#0093CC","num":"31"},
    "ALB": {"name":"ALBON",      "first":"Alexander", "team":"WILLIAMS",         "color":"#005AFF","num":"23"},
    "SAR": {"name":"SARGEANT",   "first":"Logan",     "team":"WILLIAMS",         "color":"#005AFF","num":"2"},
    "BOT": {"name":"BOTTAS",     "first":"Valtteri",  "team":"KICK SAUBER",      "color":"#52E252","num":"77"},
    "ZHO": {"name":"ZHOU",       "first":"Guanyu",    "team":"KICK SAUBER",      "color":"#52E252","num":"24"},
    "HUL": {"name":"HÜLKENBERG", "first":"Nico",      "team":"HAAS",             "color":"#B6BABD","num":"27"},
    "MAG": {"name":"MAGNUSSEN",  "first":"Kevin",     "team":"HAAS",             "color":"#B6BABD","num":"20"},
    "TSU": {"name":"TSUNODA",    "first":"Yuki",      "team":"RB",               "color":"#6692FF","num":"22"},
    "RIC": {"name":"RICCIARDO",  "first":"Daniel",    "team":"RB",               "color":"#6692FF","num":"3"},
}
TYRE_COLORS = {"SOFT":"#E8002D","MEDIUM":"#FFD700","HARD":"#F0F2F5","INTER":"#39B54A","WET":"#0067FF"}

# ── Page config ───────────────────────────────────────────────────────────────
_DIR = Path(__file__).resolve().parent

st.set_page_config(
    page_title="F1 STRATEGY AI",
    page_icon=str(_DIR / "f1.png"),
    layout="wide",
    initial_sidebar_state="expanded",
)

def _b64(p: Path) -> str:
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode()

_IMG_RED  = _b64(_DIR / "F1_RED.jpeg")
_IMG_JACK = _b64(_DIR / "JACK TEAM RACING.jpeg")

# ── CSS ───────────────────────────────────────────────────────────────────────
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Antonio:wght@100;400;700&family=Titillium+Web:ital,wght@0,200;0,300;0,400;0,600;0,700;1,400&display=swap');

:root {{
  --black:  #000000;
  --off:    #080808;
  --panel:  #0f0f0f;
  --panel2: #161616;
  --border: #1e1e1e;
  --bord2:  #2a2a2a;
  --red:    #e8002d;
  --red2:   #ff1a3e;
  --white:  #f5f5f5;
  --dim:    #555555;
  --dim2:   #333333;
  --yellow: #ffd700;
  --teal:   #00d2be;
  --orange: #ff8000;
  --green:  #39b54a;
  --font-d: 'Antonio', sans-serif;
  --font-b: 'Titillium Web', sans-serif;
}}
*, *::before, *::after {{ box-sizing: border-box; }}

html, body, .stApp {{
  background-color: var(--black);
  background-image:
    url('data:image/jpeg;base64,{IMG_RED}'),
    url('data:image/jpeg;base64,{IMG_JACK}');
  background-repeat: no-repeat, no-repeat;
  background-position: left center, right center;
  background-size: 50% auto, 50% auto;
  background-attachment: fixed, fixed;
  color: var(--white);
  font-family: var(--font-b);
}}
/* layered overlays for the photos */
.stApp::before {{
  content:'';
  position:fixed; inset:0;
  background: radial-gradient(ellipse at 25% 50%, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.92) 70%),
              radial-gradient(ellipse at 75% 50%, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.92) 70%);
  z-index:0; pointer-events:none;
}}
/* subtle scanline texture */
.stApp::after {{
  content:'';
  position:fixed; inset:0;
  background-image: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(0,0,0,0.07) 2px,
    rgba(0,0,0,0.07) 4px
  );
  z-index:0; pointer-events:none;
}}

#MainMenu, footer, header {{ visibility:hidden; }}
.stDeployButton {{ display:none; }}
[data-testid="stToolbar"] {{ display:none; }}

.main .block-container {{
  padding: 0 2rem 4rem !important;
  max-width: 1480px !important;
  position: relative;
  z-index: 1;
}}

/* ═══════════ NAV BAR ═══════════ */
.f1-nav {{
  position:sticky; top:0; z-index:200;
  background: rgba(0,0,0,0.96);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
  display:flex; align-items:stretch; height:50px;
  margin:0 -2rem; padding:0 2rem;
}}
.f1-nav-logo {{
  font-family:var(--font-d); font-size:1rem; font-weight:700;
  letter-spacing:.18em; color:var(--white);
  display:flex; align-items:center; gap:10px;
  padding-right:1.8rem; border-right:1px solid var(--border);
  white-space:nowrap; text-transform:uppercase;
}}
.f1-nav-dot {{
  width:7px; height:7px; background:var(--red); border-radius:50%;
  animation: pulse 2s ease-in-out infinite;
}}
@keyframes pulse {{ 0%,100%{{opacity:1;transform:scale(1)}} 50%{{opacity:.4;transform:scale(.75)}} }}
.f1-nav-items {{
  display:flex; align-items:center; padding:0 .6rem; flex:1;
}}
.f1-nav-item {{
  font-family:var(--font-b); font-size:.65rem; font-weight:700;
  letter-spacing:.18em; color:var(--dim); text-transform:uppercase;
  padding:0 1.1rem; height:50px;
  display:flex; align-items:center;
  border-bottom:2px solid transparent;
  transition:color .15s,border-color .15s; white-space:nowrap;
}}
.f1-nav-item.active {{ color:var(--white); border-bottom-color:var(--red); }}
.f1-nav-right {{
  display:flex; align-items:center; gap:.5rem;
  border-left:1px solid var(--border); padding-left:1rem;
  font-family:var(--font-b); font-size:.62rem; font-weight:600;
  letter-spacing:.1em; color:var(--dim); text-transform:uppercase;
}}
.f1-live-badge {{
  background:var(--red); color:white;
  font-size:.52rem; font-weight:700; letter-spacing:.2em;
  padding:2px 7px; border-radius:1px;
}}

/* ═══════════ SIDEBAR ═══════════ */
[data-testid="stSidebar"] {{
  background:var(--off) !important;
  border-right:1px solid var(--border) !important;
  min-width:276px !important; max-width:276px !important;
}}
[data-testid="stSidebar"] > div:first-child {{ padding:0 !important; }}

.sb-header {{
  padding:1.4rem 1.25rem 1rem;
  border-bottom:1px solid var(--border);
  background: linear-gradient(135deg, #0a0a0a 0%, #0f0f0f 100%);
}}
.sb-title {{
  font-family:var(--font-d); font-size:.6rem; font-weight:700;
  letter-spacing:.35em; color:var(--dim); text-transform:uppercase; margin-bottom:2px;
}}
.sb-subtitle {{
  font-family:var(--font-d); font-size:1.3rem; font-weight:700;
  letter-spacing:.05em; color:var(--white); text-transform:uppercase; line-height:1.1;
}}
.sb-subtitle span {{ color:var(--red); }}
.sb-section {{
  padding:.85rem 1.25rem .25rem;
  font-family:var(--font-b); font-size:.58rem; font-weight:700;
  letter-spacing:.28em; color:var(--dim2); text-transform:uppercase;
  border-top:1px solid var(--border); margin-top:.3rem;
}}
.drv-card {{
  margin:.45rem 1.25rem .75rem;
  background:var(--panel); border:1px solid var(--bord2);
  display:flex; align-items:center; gap:0; overflow:hidden;
  animation:drv-in .3s cubic-bezier(.22,1,.36,1);
}}
@keyframes drv-in {{ from{{opacity:0;transform:translateY(5px)}} to{{opacity:1;transform:translateY(0)}} }}
.drv-bar {{ width:4px; align-self:stretch; flex-shrink:0; }}
.drv-num {{
  font-family:var(--font-d); font-size:1.9rem; font-weight:700;
  color:var(--white); padding:.7rem .7rem .7rem .85rem; line-height:1; opacity:.85;
}}
.drv-info {{ flex:1; padding:.7rem .7rem .7rem 0; }}
.drv-first {{ font-family:var(--font-b); font-size:.6rem; font-weight:300; color:var(--dim); text-transform:uppercase; letter-spacing:.1em; line-height:1; }}
.drv-last  {{ font-family:var(--font-d); font-size:.95rem; font-weight:700; color:var(--white); text-transform:uppercase; letter-spacing:.04em; line-height:1.15; margin:1px 0; }}
.drv-team  {{ font-family:var(--font-b); font-size:.55rem; font-weight:600; letter-spacing:.12em; text-transform:uppercase; }}

/* sidebar controls */
.stSelectbox label,.stSlider label,.stRadio label,.stNumberInput label {{
  font-family:var(--font-b) !important; font-size:.6rem !important;
  font-weight:700 !important; letter-spacing:.2em !important;
  color:var(--dim) !important; text-transform:uppercase !important;
}}
[data-baseweb="select"] > div {{
  background:var(--panel) !important; border:1px solid var(--bord2) !important;
  border-radius:0 !important; color:var(--white) !important;
  font-family:var(--font-b) !important; font-size:.82rem !important; font-weight:600 !important;
}}
[data-baseweb="select"] > div:focus-within {{ border-color:var(--red) !important; box-shadow:none !important; }}
.stSlider [role="slider"] {{ background:var(--red) !important; border-color:var(--red) !important; width:13px !important; height:13px !important; }}

/* primary button */
.stButton > button[kind="primary"] {{
  background:var(--red) !important; border:none !important; border-radius:0 !important;
  font-family:var(--font-d) !important; font-size:.78rem !important; font-weight:700 !important;
  letter-spacing:.28em !important; color:white !important; padding:.8rem 1.5rem !important;
  width:100% !important; transition:background .15s,letter-spacing .2s !important; text-transform:uppercase !important;
}}
.stButton > button[kind="primary"]:hover {{ background:var(--red2) !important; letter-spacing:.38em !important; }}
.stButton > button:not([kind="primary"]) {{
  background:var(--panel) !important; border:1px solid var(--bord2) !important; border-radius:0 !important;
  font-family:var(--font-b) !important; font-size:.7rem !important; font-weight:700 !important;
  letter-spacing:.14em !important; color:var(--white) !important; padding:.62rem 1.5rem !important;
  width:100% !important; transition:border-color .15s !important;
}}
.stButton > button:not([kind="primary"]):hover {{ border-color:var(--red) !important; }}

/* ═══════════ HERO ═══════════ */
.hero {{
  padding:3rem 0 2.5rem; border-bottom:1px solid var(--border);
  position:relative; overflow:hidden;
}}
.hero-eye {{
  font-family:var(--font-b); font-size:.6rem; font-weight:700;
  letter-spacing:.35em; color:var(--red); text-transform:uppercase;
  margin-bottom:.75rem; display:flex; align-items:center; gap:10px;
}}
.hero-eye::before {{ content:''; width:24px; height:1px; background:var(--red); }}
.hero-h1 {{
  font-family:var(--font-d); font-size:clamp(2.6rem,5.5vw,5rem);
  font-weight:700; line-height:.92; text-transform:uppercase;
  letter-spacing:-.02em; color:var(--white); margin-bottom:.4rem;
}}
.hero-h1 em {{ color:var(--red); font-style:normal; }}
.hero-meta {{
  font-family:var(--font-b); font-size:.72rem; font-weight:400;
  letter-spacing:.15em; color:var(--dim); text-transform:uppercase; margin-top:1rem;
}}
.hero-meta strong {{ color:var(--white); font-weight:600; }}
.hero-car {{
  position:absolute; right:1.5rem; bottom:-10px; opacity:.055;
  pointer-events:none; animation:idle 4s ease-in-out infinite;
}}
@keyframes idle {{ 0%,100%{{transform:translateY(0)}} 50%{{transform:translateY(-5px)}} }}

/* ═══════════ METRIC STRIP ═══════════ */
.metric-strip {{
  display:grid; grid-template-columns:repeat(4,1fr);
  border-bottom:1px solid var(--border);
  animation:fade-up .45s ease-out;
}}
@keyframes fade-up {{ from{{opacity:0;transform:translateY(-6px)}} to{{opacity:1;transform:translateY(0)}} }}
.mc {{
  padding:1.5rem 1.7rem; border-right:1px solid var(--border);
  position:relative; transition:background .2s;
}}
.mc:last-child {{ border-right:none; }}
.mc:hover {{ background:var(--panel); }}
.mc::before {{
  content:''; position:absolute; top:0;left:0;right:0; height:2px;
  background:var(--red); transform:scaleX(0); transform-origin:left;
  transition:transform .28s ease;
}}
.mc:hover::before {{ transform:scaleX(1); }}
.mc-lbl {{
  font-family:var(--font-b); font-size:.55rem; font-weight:700;
  letter-spacing:.28em; color:var(--dim); text-transform:uppercase; margin-bottom:.45rem;
}}
.mc-val {{
  font-family:var(--font-d); font-size:2.1rem; font-weight:700;
  color:var(--white); line-height:1; letter-spacing:-.02em;
}}
.mc-val.red    {{ color:var(--red); }}
.mc-val.teal   {{ color:var(--teal); }}
.mc-val.gold   {{ color:var(--yellow); }}
.mc-val.orange {{ color:var(--orange); }}
.mc-unit  {{ font-family:var(--font-b); font-size:.65rem; color:var(--dim); margin-left:2px; }}
.mc-sub   {{ font-family:var(--font-b); font-size:.62rem; color:var(--dim); margin-top:4px; letter-spacing:.04em; }}

/* ═══════════ TABS ═══════════ */
.stTabs [data-baseweb="tab-list"] {{
  background:var(--black) !important; border-bottom:1px solid var(--border) !important;
  gap:0 !important; padding:0 !important;
}}
.stTabs [data-baseweb="tab"] {{
  background:transparent !important; color:var(--dim) !important;
  font-family:var(--font-b) !important; font-size:.65rem !important;
  font-weight:700 !important; letter-spacing:.18em !important;
  text-transform:uppercase !important; padding:.95rem 1.5rem !important;
  border:none !important; border-bottom:2px solid transparent !important;
  border-radius:0 !important; transition:color .15s,border-color .15s !important;
  white-space:nowrap !important;
}}
.stTabs [data-baseweb="tab"]:hover {{ color:var(--white) !important; background:var(--panel) !important; }}
.stTabs [aria-selected="true"] {{ color:var(--white) !important; border-bottom-color:var(--red) !important; background:transparent !important; }}
.stTabs [data-baseweb="tab-panel"] {{ padding:2rem 0 0 !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ display:none !important; }}

/* ═══════════ SECTION HEADS ═══════════ */
.sh {{
  font-family:var(--font-d); font-size:.62rem; font-weight:700;
  letter-spacing:.35em; color:var(--dim); text-transform:uppercase;
  margin:2rem 0 1rem; display:flex; align-items:center; gap:14px;
}}
.sh::after {{ content:''; flex:1; height:1px; background:var(--border); }}
.sh span {{ color:var(--white); }}

/* ═══════════ DATA TABLE ═══════════ */
.stDataFrame {{ border:1px solid var(--border) !important; border-radius:0 !important; }}
.stDataFrame table {{ font-family:var(--font-b) !important; font-size:.77rem !important; }}
.stDataFrame thead th {{
  background:var(--panel) !important; color:var(--dim) !important;
  font-size:.58rem !important; font-weight:700 !important;
  letter-spacing:.18em !important; text-transform:uppercase !important;
  border-bottom:1px solid var(--border) !important; padding:.55rem .8rem !important;
}}
.stDataFrame tbody tr:hover td {{ background:var(--panel) !important; }}

/* ═══════════ ALERTS ═══════════ */
.stAlert {{
  background:var(--panel) !important; border:1px solid var(--bord2) !important;
  border-left:2px solid var(--red) !important; border-radius:0 !important;
  font-family:var(--font-b) !important; font-size:.78rem !important;
}}

/* ═══════════ MISC ═══════════ */
.stSpinner > div {{ border-top-color:var(--red) !important; }}
hr {{ border-color:var(--border) !important; margin:1.5rem 0 !important; }}
::-webkit-scrollbar {{ width:4px; height:4px; }}
::-webkit-scrollbar-track {{ background:var(--black); }}
::-webkit-scrollbar-thumb {{ background:var(--bord2); }}
::-webkit-scrollbar-thumb:hover {{ background:var(--red); }}
.stDownloadButton button {{
  background:transparent !important; border:1px solid var(--bord2) !important;
  border-radius:0 !important; font-family:var(--font-b) !important;
  font-size:.66rem !important; font-weight:700 !important;
  letter-spacing:.18em !important; color:var(--white) !important;
  padding:.58rem 1.4rem !important; transition:border-color .15s,background .15s !important;
}}
.stDownloadButton button:hover {{
  border-color:var(--red) !important; background:rgba(232,0,45,.06) !important;
}}
.stNumberInput input {{
  background:var(--panel) !important; border:1px solid var(--bord2) !important;
  border-radius:0 !important; color:var(--white) !important;
  font-family:var(--font-b) !important; font-size:.82rem !important;
}}

/* success bar */
.sbar {{
  background:rgba(232,0,45,.05); border:1px solid rgba(232,0,45,.15);
  border-left:2px solid var(--red); padding:.85rem 1.4rem;
  font-family:var(--font-b); font-size:.76rem; color:var(--dim);
  letter-spacing:.04em; animation:fade-in .4s ease-out;
}}
@keyframes fade-in {{ from{{opacity:0}} to{{opacity:1}} }}
.sbar strong {{ color:var(--white); }}

/* rec panel */
.rec-panel {{
  background:var(--panel); border:1px solid var(--bord2);
  border-left:3px solid var(--yellow); padding:1.1rem 1.5rem;
  margin:1rem 0 1.4rem; animation:drv-in .4s ease-out;
}}
.rec-label {{
  font-family:var(--font-b); font-size:.56rem; font-weight:700;
  letter-spacing:.28em; color:var(--dim); text-transform:uppercase; margin-bottom:.45rem;
}}
.rec-text {{ font-family:var(--font-b); font-size:.82rem; color:var(--white); line-height:1.6; }}
.hl-red   {{ color:var(--red);    font-weight:700; }}
.hl-gold  {{ color:var(--yellow); font-weight:700; }}
.hl-teal  {{ color:var(--teal);   font-weight:700; }}

/* grid panels */
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:1px; background:var(--border); border:1px solid var(--border); }}
.grid3 {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:1px; background:var(--border); border:1px solid var(--border); }}
.gpanel {{
  background:var(--off); padding:1.2rem 1.6rem;
  transition:background .2s;
}}
.gpanel:hover {{ background:var(--panel); }}
.gpanel-lbl {{ font-family:var(--font-b); font-size:.56rem; font-weight:700; letter-spacing:.28em; color:var(--dim); text-transform:uppercase; margin-bottom:4px; }}
.gpanel-val {{ font-family:var(--font-d); font-size:1.05rem; font-weight:700; color:var(--white); }}
.gpanel-sub {{ font-family:var(--font-b); font-size:.66rem; color:var(--dim); margin-top:3px; }}

/* landing feature cards */
.feat-grid {{
  display:grid; grid-template-columns:repeat(3,1fr);
  gap:1px; background:var(--border); border:1px solid var(--border);
  margin:2.5rem 0 1.5rem;
  animation:fade-in .7s ease-out;
}}
.feat-card {{
  background:var(--off); padding:2rem 1.8rem;
  transition:background .2s; position:relative; overflow:hidden;
}}
.feat-card:hover {{ background:var(--panel); }}
.feat-card::before {{
  content:''; position:absolute; top:0;left:0;right:0; height:2px;
  background:var(--red); transform:scaleX(0); transform-origin:left;
  transition:transform .3s ease;
}}
.feat-card:hover::before {{ transform:scaleX(1); }}
.feat-icon {{ font-size:1.4rem; margin-bottom:.75rem; }}
.feat-title {{
  font-family:var(--font-d); font-size:1rem; font-weight:700;
  color:var(--white); text-transform:uppercase; letter-spacing:.04em; margin-bottom:.35rem;
}}
.feat-body {{
  font-family:var(--font-b); font-size:.7rem; color:var(--dim);
  line-height:1.55; letter-spacing:.02em;
}}
.feat-badge {{
  display:inline-block; margin-top:.7rem;
  font-family:var(--font-b); font-size:.55rem; font-weight:700;
  letter-spacing:.18em; color:var(--red); text-transform:uppercase;
  border:1px solid rgba(232,0,45,.25); padding:2px 8px;
}}
.landing-cta {{
  background:var(--panel); border:1px solid var(--bord2);
  border-left:2px solid var(--dim2); padding:1.1rem 1.5rem;
  font-family:var(--font-b); font-size:.8rem; color:var(--dim);
  animation:fade-in 1s ease-out;
}}

/* rival comparison */
.rival-compare {{
  display:grid; grid-template-columns:1fr auto 1fr;
  align-items:center; gap:1rem;
  padding:1.5rem 0; border-bottom:1px solid var(--border); margin-bottom:1.5rem;
}}
.rival-vs {{
  font-family:var(--font-d); font-size:1.7rem; font-weight:700;
  color:var(--dim2); text-align:center;
}}

/* top-5 rank cards */
.rank-card {{
  border:1px solid var(--border); padding:.75rem 1rem;
  margin-bottom:.45rem; background:var(--off);
  transition:background .2s, border-color .2s;
}}
.rank-card:hover {{ background:var(--panel); border-color:var(--bord2); }}
.rank-num  {{ font-family:var(--font-b); font-size:.56rem; letter-spacing:.18em; color:var(--dim); text-transform:uppercase; margin-bottom:2px; }}
.rank-strat {{ font-family:var(--font-d); font-size:.88rem; font-weight:700; color:var(--white); letter-spacing:.04em; }}
.rank-meta  {{ font-family:var(--font-b); font-size:.62rem; color:var(--dim); margin-top:2px; }}

/* cliff badge */
.cliff-badge {{
  display:inline-flex; align-items:center; gap:5px;
  font-family:var(--font-b); font-size:.58rem; font-weight:700;
  letter-spacing:.1em; color:var(--red); text-transform:uppercase;
  margin-top:5px;
}}
.cliff-none {{ color:var(--dim2); }}
.mode-badge {{
  display:inline-block; font-size:.55rem; font-weight:700;
  letter-spacing:.12em; padding:1px 6px; border-radius:1px;
  text-transform:uppercase;
}}

/* ═══════════ WEATHER CHIP (F1-app inspired) ═══════════ */
.weather-strip {{
  display:flex; align-items:stretch; gap:0;
  border:1px solid var(--border); background:var(--off);
  margin:1.5rem 0; animation:fade-up .5s ease-out;
}}
.wchip {{
  padding:.8rem 1.4rem; border-right:1px solid var(--border);
  display:flex; align-items:center; gap:10px; flex:1;
}}
.wchip:last-child {{ border-right:none; }}
.wchip-icon {{ font-size:1.3rem; opacity:.85; }}
.wchip-lbl {{ font-family:var(--font-b); font-size:.52rem; font-weight:700; letter-spacing:.2em; color:var(--dim); text-transform:uppercase; }}
.wchip-val {{ font-family:var(--font-d); font-size:1.05rem; font-weight:700; color:var(--white); line-height:1.1; }}
.wchip-val.hot   {{ color:var(--red); }}
.wchip-val.cold  {{ color:#4c9be8; }}
.wchip-val.rain  {{ color:var(--teal); }}

/* ═══════════ TIMING TOWER (F1-app inspired) ═══════════ */
.tt-wrap {{
  border:1px solid var(--border); background:var(--off); margin:1rem 0;
}}
.tt-head {{
  padding:.6rem 1.2rem; border-bottom:1px solid var(--border);
  display:flex; align-items:center; justify-content:space-between;
  font-family:var(--font-b); font-size:.56rem; font-weight:700;
  letter-spacing:.25em; color:var(--dim); text-transform:uppercase;
}}
.tt-row {{
  display:grid; grid-template-columns:32px 28px 1fr auto auto;
  align-items:center; gap:12px; padding:.55rem 1.2rem;
  border-bottom:1px solid #111; transition:background .15s;
}}
.tt-row:last-child {{ border-bottom:none; }}
.tt-row:hover {{ background:var(--panel); }}
.tt-row.self {{ background:rgba(232,0,45,.05); border-left:2px solid var(--red); }}
.tt-pos {{ font-family:var(--font-d); font-size:.85rem; font-weight:700; color:var(--dim); }}
.tt-pos.p1 {{ color:var(--yellow); }}
.tt-pos.p2 {{ color:#c0c0c0; }}
.tt-pos.p3 {{ color:#cd7f32; }}
.tt-team-bar {{ width:3px; height:20px; border-radius:1px; }}
.tt-driver {{ font-family:var(--font-d); font-size:.82rem; font-weight:700; color:var(--white); letter-spacing:.04em; }}
.tt-team {{ font-family:var(--font-b); font-size:.56rem; color:var(--dim); letter-spacing:.06em; margin-top:1px; }}
.tt-time {{ font-family:var(--font-b); font-size:.72rem; font-weight:600; color:var(--dim); text-align:right; }}
.tt-status {{ font-family:var(--font-b); font-size:.58rem; font-weight:700; letter-spacing:.1em; text-align:right; text-transform:uppercase; }}

/* ═══════════ COMPOUND ROUNDEL (F1-app tyre icon) ═══════════ */
.roundel {{
  display:inline-flex; align-items:center; justify-content:center;
  width:22px; height:22px; border-radius:50%; border:2px solid;
  font-family:var(--font-d); font-size:.62rem; font-weight:700;
  flex-shrink:0;
}}
.roundel.soft   {{ border-color:var(--red);    color:var(--red);    background:rgba(232,0,45,.08); }}
.roundel.medium {{ border-color:var(--yellow); color:var(--yellow); background:rgba(255,215,0,.08); }}
.roundel.hard   {{ border-color:#f0ede8;       color:#f0ede8;       background:rgba(240,237,232,.06); }}

/* ═══════════ COMPARISON PILL (undercut vs overcut) ═══════════ */
.strat-pill {{
  display:inline-flex; align-items:center; gap:6px;
  padding:3px 10px; border-radius:2px; font-family:var(--font-b);
  font-size:.62rem; font-weight:700; letter-spacing:.1em; text-transform:uppercase;
}}
.strat-pill.win  {{ background:rgba(57,181,74,.12); color:var(--green); border:1px solid rgba(57,181,74,.3); }}
.strat-pill.lose {{ background:rgba(85,85,85,.12); color:var(--dim); border:1px solid var(--bord2); }}
</style>
""".format(IMG_RED=_IMG_RED, IMG_JACK=_IMG_JACK)

st.markdown(_CSS, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div class="sb-header">
      <div class="sb-title">Monte Carlo Engine</div>
      <div class="sb-subtitle">F1 <span>Strategy</span><br>Intelligence</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sb-section">Session</div>', unsafe_allow_html=True)

    @st.cache_data(show_spinner=False, ttl=86400)  # refresh once a day
    def _get_latest_year():
        return get_latest_available_year()

    latest_year = _get_latest_year()
    # Always starts at whatever FastF1 currently has completed-race data
    # for — no manual bump needed when a new season starts. 2018 is the
    # practical floor: FastF1's lap-level telemetry is reliable from here.
    year_options = list(range(latest_year, 2017, -1))
    year = st.selectbox("SEASON", year_options, index=0, label_visibility="collapsed")

    @st.cache_data(show_spinner=False)
    def _get_races(y):
        # Only the latest season needs future-race filtering — past
        # seasons are entirely in the past already.
        return get_race_schedule(y, only_completed=(y == latest_year))
    race_list = _get_races(year)
    if not race_list:
        st.warning(f"No completed races found yet for {year}.")
        st.stop()
    race = st.selectbox("GRAND PRIX", race_list, index=0)

    st.markdown('<div class="sb-section">Driver</div>', unsafe_allow_html=True)
    driver_code = st.selectbox("SELECT DRIVER", list(DRIVERS.keys()), index=0)
    drv = DRIVERS[driver_code]
    st.markdown(f"""
    <div class="drv-card">
      <div class="drv-bar" style="background:{drv['color']}"></div>
      <div class="drv-num">{drv['num']}</div>
      <div class="drv-info">
        <div class="drv-first">{drv['first']}</div>
        <div class="drv-last">{drv['name']}</div>
        <div class="drv-team" style="color:{drv['color']}">{drv['team']}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sb-section">Simulation</div>', unsafe_allow_html=True)
    n_sims        = st.slider("MC ITERATIONS", 100, 2000, N_SIMULATIONS, step=100)
    stop_strategy = st.radio("STRATEGY TYPE", ["1-stop","2-stop","Both"])
    noise         = st.slider("LAP TIME NOISE (s)", 0.0, 1.0, 0.3, step=0.05)

    st.markdown('<div class="sb-section">Track Conditions</div>', unsafe_allow_html=True)
    use_live_temp = st.checkbox("Use live session temperature", value=True)
    manual_temp   = None
    if not use_live_temp:
        manual_temp = st.slider("Track temp override (°C)", 15, 55, 35)

    st.markdown("<br>", unsafe_allow_html=True)
    run_btn = st.button("▶  RUN SIMULATION", use_container_width=True, type="primary")
    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(f"""
    <div style="padding:.9rem 1.25rem;border-top:1px solid var(--border);
                font-family:'Titillium Web',sans-serif;font-size:.56rem;
                font-weight:600;letter-spacing:.14em;color:#333;text-transform:uppercase">
      {year} SEASON · {race.upper()} GP<br>
      <span style="color:#1e1e1e;margin-top:3px;display:block">POWERED BY FASTF1 + PWLF</span>
    </div>
    """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# TOP NAV
# ═══════════════════════════════════════════════════════════════════
st.markdown(f"""
<div class="f1-nav">
  <div class="f1-nav-logo"><div class="f1-nav-dot"></div>F1 Strategy AI</div>
  <div class="f1-nav-items">
    <div class="f1-nav-item active">Strategy</div>
    <div class="f1-nav-item">Tyre Model</div>
    <div class="f1-nav-item">Rival Analysis</div>
    <div class="f1-nav-item">Results</div>
    <div class="f1-nav-item">Backtest</div>
  </div>
  <div class="f1-nav-right">
    <span class="f1-live-badge">AI</span>{year} · {race}
  </div>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# HERO
# ═══════════════════════════════════════════════════════════════════
st.markdown(f"""
<div class="hero">
  <div class="hero-eye">Monte Carlo Pit Stop Optimiser</div>
  <div class="hero-h1">F1 <em>Strategy</em><br>Intelligence</div>
  <div class="hero-meta">
    <strong>{year}</strong> Season &nbsp;·&nbsp;
    <strong>{race}</strong> Grand Prix &nbsp;·&nbsp;
    <strong style="color:{drv['color']}">{drv['first']} {drv['name']}</strong>
    &nbsp;·&nbsp; {drv['team']}
  </div>
  <div class="hero-car">
    <svg width="580" height="130" viewBox="0 0 640 140" fill="white" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="320" cy="82" rx="260" ry="24"/>
      <polygon points="555,82 625,79 625,85"/>
      <ellipse cx="312" cy="60" rx="68" ry="22"/>
      <rect x="279" y="44" width="64" height="6" rx="2"/>
      <rect x="279" y="44" width="6" height="28" rx="2"/>
      <rect x="337" y="44" width="6" height="28" rx="2"/>
      <rect x="496" y="98" width="112" height="8" rx="1"/>
      <rect x="489" y="84" width="8" height="24" rx="1"/>
      <rect x="606" y="86" width="16" height="5" rx="1"/>
      <rect x="606" y="100" width="16" height="5" rx="1"/>
      <rect x="48" y="42" width="96" height="10" rx="1"/>
      <rect x="72" y="52" width="48" height="5" rx="1"/>
      <rect x="48" y="42" width="6" height="36" rx="1"/>
      <rect x="138" y="42" width="6" height="36" rx="1"/>
      <ellipse cx="488" cy="110" rx="22" ry="22"/>
      <ellipse cx="488" cy="110" rx="13" ry="13" fill="black"/>
      <ellipse cx="144" cy="112" rx="27" ry="27"/>
      <ellipse cx="144" cy="112" rx="16" ry="16" fill="black"/>
    </svg>
  </div>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# LANDING STATE — animated feature cards with real capabilities
# ═══════════════════════════════════════════════════════════════════
if not run_btn:
    st.markdown(f"""
    <div class="feat-grid">
      <div class="feat-card">
        <div class="feat-icon">◈</div>
        <div class="feat-title">Monte Carlo Simulation</div>
        <div class="feat-body">
          Evaluates every valid 1-stop and 2-stop strategy combination
          across up to <strong style="color:#f5f5f5">{n_sims:,} iterations</strong> with
          configurable lap-time noise. Returns P10/P50/P90 distributions and
          per-strategy win rates — not just a point estimate.
        </div>
        <div class="feat-badge">Active · {n_sims:,} sims</div>
      </div>
      <div class="feat-card">
        <div class="feat-icon">◬</div>
        <div class="feat-title">3-Phase Tyre Model</div>
        <div class="feat-body">
          Piecewise linear fit across <em>bedding → plateau → cliff</em> phases
          using real FastF1 lap data. Cliff lap estimated with 95 % confidence interval.
          Driver-specific: <strong style="color:#f5f5f5">{driver_code}</strong>'s laps
          weighted 4× above fleet for personalised deg curves.
        </div>
        <div class="feat-badge">pwlf · driver-weighted</div>
      </div>
      <div class="feat-card">
        <div class="feat-icon">⊕</div>
        <div class="feat-title">Rival Undercut Engine</div>
        <div class="feat-body">
          Configure any rival car's compound and tyre age, set the gap,
          and scan a lap window for undercut EV. Returns mean EV, P10–P90 band,
          win rate per lap, and a head-to-head Monte Carlo across candidate strategies.
        </div>
        <div class="feat-badge">EV + H2H MC</div>
      </div>
      <div class="feat-card">
        <div class="feat-icon">▶</div>
        <div class="feat-title">Strategy Comparison</div>
        <div class="feat-body">
          Ranked bar chart of top strategies coloured by first compound,
          with mean ± std error bars and win rate labels.
          Lap-by-lap time trace for top 3 strategies with pit stop markers.
        </div>
        <div class="feat-badge">{'1-stop' if stop_strategy == '1-stop' else '2-stop' if stop_strategy == '2-stop' else '1 + 2-stop'} mode</div>
      </div>
      <div class="feat-card">
        <div class="feat-icon">⊘</div>
        <div class="feat-title">Backtest Mode</div>
        <div class="feat-body">
          Reconstructs what <strong style="color:#f5f5f5">{driver_code}</strong> actually did
          from FastF1 stint data — compound sequence, pit laps, durations —
          and compares deterministic race time against the AI optimal strategy.
        </div>
        <div class="feat-badge">actual vs ai optimal</div>
      </div>
      <div class="feat-card">
        <div class="feat-icon">◎</div>
        <div class="feat-title">Live FastF1 Data</div>
        <div class="feat-body">
          Race schedule loaded dynamically for <strong style="color:#f5f5f5">{year}</strong>,
          race laps pulled from session metadata, pit loss estimated from real
          in/out lap timing. No hardcoded season values — every year, every circuit.
        </div>
        <div class="feat-badge">{year} · {race} GP</div>
      </div>
    </div>
    <div class="landing-cta">
      Select your session in the sidebar — season, race, driver and simulation parameters —
      then press <strong style="color:#f5f5f5">▶ RUN SIMULATION</strong> to begin.
      All {len(race_list)} {year} events available.
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ═══════════════════════════════════════════════════════════════════
# MATPLOTLIB THEME
# ═══════════════════════════════════════════════════════════════════
plt.rcParams.update({
    "figure.facecolor": "#000000", "axes.facecolor":   "#0d0d0d",
    "axes.edgecolor":   "#1e1e1e", "axes.labelcolor":  "#555555",
    "axes.labelsize":   8,         "axes.titlesize":   9,
    "axes.titlecolor":  "#f5f5f5", "xtick.color":      "#444444",
    "ytick.color":      "#444444", "xtick.labelsize":  7.5,
    "ytick.labelsize":  7.5,       "text.color":       "#f5f5f5",
    "grid.color":       "#1e1e1e", "grid.linestyle":   "-",
    "grid.linewidth":   0.4,       "legend.facecolor": "#111111",
    "legend.edgecolor": "#1e1e1e", "legend.fontsize":  7.5,
    "font.family":      ["Titillium Web", "monospace"],
    "figure.dpi":       130,
})

# ═══════════════════════════════════════════════════════════════════
# DATA PIPELINE
# ═══════════════════════════════════════════════════════════════════
with st.spinner("Loading FastF1 session data…"):
    try:
        session         = load_session(year, race)
        laps_raw        = get_laps(session)
        pit_stops       = get_pit_stops(session)
        race_total_laps = get_race_laps(session)
        session_drivers = get_session_drivers(session)
        weather         = get_track_temp(session)
        classification  = get_final_classification(session, top_n=8)
    except Exception as e:
        st.error(f"Failed to load session: {e}")
        st.stop()

with st.spinner("Cleaning & feature engineering…"):
    laps = clean_laps(laps_raw)
    laps = engineer_features(laps, total_laps=race_total_laps)

with st.spinner("Fitting 3-phase tyre degradation model…"):
    deg_model = TyreDegModel()
    deg_model.fit(laps, driver=driver_code)
    pit_loss = get_pit_loss(pit_stops)

    # Track temperature scaling — live session data unless overridden
    effective_temp = manual_temp if not use_live_temp else (weather["track_temp"] if weather else None)
    deg_model.set_track_temp(effective_temp)

with st.spinner(f"Running {n_sims:,} Monte Carlo simulations…"):
    strategies = []
    if stop_strategy in ["1-stop", "Both"]:
        strategies += generate_one_stop_strategies(race_total_laps)
    if stop_strategy in ["2-stop", "Both"]:
        strategies += generate_two_stop_strategies(race_total_laps)
    mc_results = run_monte_carlo(
        strategies, deg_model, pit_loss,
        n_simulations=n_sims, noise_std=noise,
    )

# ═══════════════════════════════════════════════════════════════════
# SUCCESS BAR
# ═══════════════════════════════════════════════════════════════════
best_row = mc_results.iloc[0]
st.markdown(f"""
<div class="sbar">
  ✓ &nbsp;
  <strong>{len(strategies):,} strategies</strong> evaluated ·
  <strong>{n_sims:,} iterations</strong> ·
  Optimal: <strong>{best_row['strategy']}</strong> ·
  Win rate: <strong>{best_row['win_rate']:.0%}</strong>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# METRIC STRIP
# ═══════════════════════════════════════════════════════════════════
worst = mc_results.iloc[-1]
delta_vs_worst = worst["mean_time"] - best_row["mean_time"]
cliff_soft = deg_model.cliff_lap("SOFT")
cliff_str  = f"L{cliff_soft:.0f}" if cliff_soft else "—"

st.markdown(f"""
<div class="metric-strip">
  <div class="mc">
    <div class="mc-lbl">Optimal Strategy</div>
    <div class="mc-val red" style="font-size:1.25rem;margin-top:4px">{best_row['strategy']}</div>
    <div class="mc-sub">{best_row['pit_count']}-stop · {best_row['compounds']}</div>
  </div>
  <div class="mc">
    <div class="mc-lbl">Mean Race Time</div>
    <div class="mc-val">{best_row['mean_time']:.1f}<span class="mc-unit">s</span></div>
    <div class="mc-sub">± {best_row['std_time']:.1f}s uncertainty</div>
  </div>
  <div class="mc">
    <div class="mc-lbl">Win Rate</div>
    <div class="mc-val gold">{best_row['win_rate']:.1%}</div>
    <div class="mc-sub">{n_sims:,} MC iterations · p50={best_row['p50']:.1f}s</div>
  </div>
  <div class="mc">
    <div class="mc-lbl">SOFT Cliff Lap</div>
    <div class="mc-val {'red' if cliff_soft else ''}">{cliff_str}</div>
    <div class="mc-sub">{'pit urgency rising' if cliff_soft else 'no cliff detected'}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Weather strip (F1-app inspired) ──────────────────────────────────────────
if weather:
    temp_class = "hot" if weather["track_temp"] >= 42 else ("cold" if weather["track_temp"] <= 25 else "")
    rain_icon  = "🌧" if weather["rainfall"] else "☀"
    rain_class = "rain" if weather["rainfall"] else ""
    scale_note = (f"{deg_model.temp_scale:.2f}× deg scaling"
                  if deg_model.temp_scale != 1.0 else "neutral (no scaling)")
    st.markdown(f"""
    <div class="weather-strip">
      <div class="wchip">
        <div class="wchip-icon">🌡</div>
        <div>
          <div class="wchip-lbl">Track Temp</div>
          <div class="wchip-val {temp_class}">{weather['track_temp']}°C</div>
        </div>
      </div>
      <div class="wchip">
        <div class="wchip-icon">💨</div>
        <div>
          <div class="wchip-lbl">Air Temp</div>
          <div class="wchip-val">{weather['air_temp']}°C</div>
        </div>
      </div>
      <div class="wchip">
        <div class="wchip-icon">{rain_icon}</div>
        <div>
          <div class="wchip-lbl">Conditions</div>
          <div class="wchip-val {rain_class}">{'Wet' if weather['rainfall'] else 'Dry'}</div>
        </div>
      </div>
      <div class="wchip">
        <div class="wchip-icon">◈</div>
        <div>
          <div class="wchip-lbl">Deg Model Adjustment</div>
          <div class="wchip-val" style="font-size:.82rem">{scale_note}</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="weather-strip">
      <div class="wchip">
        <div class="wchip-icon">—</div>
        <div>
          <div class="wchip-lbl">Weather Data</div>
          <div class="wchip-val" style="font-size:.8rem;color:#444">Unavailable for this session</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# ── Timing tower (F1-app inspired) ───────────────────────────────────────────
if not classification.empty:
    tt_rows_html = ""
    for _, row in classification.iterrows():
        pos      = row.get("Position", "—")
        pos_cls  = f"p{int(pos)}" if str(pos).replace(".0","").isdigit() and int(float(pos)) <= 3 else ""
        drv_code = str(row.get("Driver", "—"))
        team     = str(row.get("TeamName", ""))
        time_val = str(row.get("Time", "—"))
        status   = str(row.get("Status", ""))
        is_self  = drv_code == driver_code
        drv_meta = DRIVERS.get(drv_code, {"color": "#666"})
        team_color = drv_meta["color"]

        # Clean up time display
        if "0 days" in time_val:
            time_val = time_val.split("0 days ")[-1]
        status_color = "#39b54a" if status.lower() == "finished" else "#e8002d"

        tt_rows_html += f"""
        <div class="tt-row {'self' if is_self else ''}">
          <div class="tt-pos {pos_cls}">{int(float(pos)) if str(pos).replace('.0','').isdigit() else pos}</div>
          <div class="tt-team-bar" style="background:{team_color}"></div>
          <div>
            <div class="tt-driver">{drv_code}</div>
            <div class="tt-team">{team}</div>
          </div>
          <div class="tt-time">{time_val[:12]}</div>
          <div class="tt-status" style="color:{status_color}">{status}</div>
        </div>
        """

    st.markdown(f"""
    <div class="tt-wrap">
      <div class="tt-head">
        <span>Timing Tower — Actual Result</span>
        <span>{year} {race} GP</span>
      </div>
      {tt_rows_html}
    </div>
    """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Strategy Comparison",
    "Undercut Window",
    "Tyre Model",
    "Results & Backtest",
    "Rival Analysis",
])

# ── TAB 1: STRATEGY COMPARISON ───────────────────────────────────
with tab1:
    col_l, col_r = st.columns([3, 1])

    with col_l:
        st.markdown('<div class="sh"><span>Top Strategies</span> — Mean Race Time Delta</div>', unsafe_allow_html=True)
        fig_strat = plot_strategy_comparison(mc_results, top_n=15, save=False)
        st.pyplot(fig_strat, use_container_width=True)

    with col_r:
        st.markdown('<div class="sh"><span>Podium</span></div>', unsafe_allow_html=True)
        rank_colours = ["#FFD700","#C0C0C0","#CD7F32","#555","#333"]
        for i, (_, row) in enumerate(mc_results.head(5).iterrows()):
            rc = rank_colours[i]
            st.markdown(f"""
            <div class="rank-card" style="border-left:3px solid {rc}">
              <div class="rank-num">#{i+1}</div>
              <div class="rank-strat">{row['strategy']}</div>
              <div class="rank-meta">
                {row['mean_time']:.2f}s &nbsp;·&nbsp;
                {row['win_rate']:.1%} win &nbsp;·&nbsp;
                ±{row['std_time']:.1f}s
              </div>
            </div>
            """, unsafe_allow_html=True)

        # P10/P50/P90 for best
        st.markdown('<div class="sh"><span>Dist.</span></div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:var(--border);border:1px solid var(--border)">
          <div style="background:var(--off);padding:.8rem .9rem;text-align:center">
            <div style="font-family:'Titillium Web';font-size:.52rem;font-weight:700;letter-spacing:.2em;color:var(--dim);text-transform:uppercase">P10</div>
            <div style="font-family:'Antonio';font-size:1rem;font-weight:700;color:#4c9be8">{best_row['p10']:.1f}s</div>
          </div>
          <div style="background:var(--off);padding:.8rem .9rem;text-align:center">
            <div style="font-family:'Titillium Web';font-size:.52rem;font-weight:700;letter-spacing:.2em;color:var(--dim);text-transform:uppercase">P50</div>
            <div style="font-family:'Antonio';font-size:1rem;font-weight:700;color:#f5f5f5">{best_row['p50']:.1f}s</div>
          </div>
          <div style="background:var(--off);padding:.8rem .9rem;text-align:center">
            <div style="font-family:'Titillium Web';font-size:.52rem;font-weight:700;letter-spacing:.2em;color:var(--dim);text-transform:uppercase">P90</div>
            <div style="font-family:'Antonio';font-size:1rem;font-weight:700;color:#e8002d">{best_row['p90']:.1f}s</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="sh"><span>Lap Trace</span> — Top 3 Strategies</div>', unsafe_allow_html=True)
    top3   = mc_results.head(3)
    traces = [simulate_race(row["strategy_obj"], deg_model, pit_loss, noise_std=0.0)
              for _, row in top3.iterrows()]
    fig_trace = plot_lap_trace(traces, labels=list(top3["strategy"]), save=False)
    st.pyplot(fig_trace, use_container_width=True)

# ── TAB 2: UNDERCUT WINDOW ────────────────────────────────────────
with tab2:
    st.markdown('<div class="sh"><span>Undercut Window</span> — Pit Lap Heatmap by Compound Pair</div>', unsafe_allow_html=True)
    fig_uw = plot_undercut_window(mc_results, race_total_laps, save=False)
    if fig_uw:
        st.pyplot(fig_uw, use_container_width=True)
        # Key insight block
        one_stop = mc_results[mc_results["pit_count"] == 1]
        if not one_stop.empty:
            best_1s = one_stop.iloc[0]
            try:
                best_pit = int(str(best_1s['strategy']).split("(")[1].split(")")[0])
                window_lo = max(1, best_pit - 3)
                window_hi = min(race_total_laps, best_pit + 3)
                st.markdown(f"""
                <div class="rec-panel">
                  <div class="rec-label">Optimal Pit Window</div>
                  <div class="rec-text">
                    Best 1-stop: <span class="hl-red">{best_1s['strategy']}</span>
                    &nbsp;·&nbsp; Pit lap <span class="hl-gold">{best_pit}</span>
                    &nbsp;·&nbsp; Window <span class="hl-teal">L{window_lo}–L{window_hi}</span>
                    &nbsp;·&nbsp; Win rate <span class="hl-red">{best_1s['win_rate']:.0%}</span>
                  </div>
                </div>
                """, unsafe_allow_html=True)
            except Exception:
                pass
    else:
        st.warning("No 1-stop strategies found — switch strategy type to include 1-stop.")

# ── TAB 3: TYRE MODEL ────────────────────────────────────────────
with tab3:
    col_a, col_b = st.columns([2.2, 1])
    with col_a:
        temp_note = (
            f'<span style="color:#e8002d">{deg_model.track_temp}°C · {deg_model.temp_scale:.2f}× scaling applied</span>'
            if deg_model.temp_scale != 1.0
            else '<span style="color:#333">neutral temp — no scaling</span>'
        )
        st.markdown(f'<div class="sh"><span>Degradation Curves</span> — 3-Phase Piecewise Model &nbsp;·&nbsp; {temp_note}</div>', unsafe_allow_html=True)
        fig_deg = plot_degradation_curves(deg_model, save=False)
        st.pyplot(fig_deg, use_container_width=True)

    with col_b:
        st.markdown('<div class="sh"><span>Model Summary</span></div>', unsafe_allow_html=True)
        sumdf = deg_model.summary()
        st.dataframe(sumdf, use_container_width=True, hide_index=True)

        st.markdown('<div class="sh"><span>Compound Detail</span></div>', unsafe_allow_html=True)
        for _, row in sumdf.iterrows():
            cmpd         = row["Compound"]
            color        = TYRE_COLORS.get(cmpd, "#888")
            cliff_val    = row.get("Cliff lap", "—")
            cliff_ci_val = row.get("Cliff CI (95%)", "—")
            fit_mode     = row.get("Fit mode", "")
            n_laps       = row.get("Training laps", "")
            mode_color   = {"full":"#39B54A","fallback":"#FFD700"}.get(fit_mode, "#333")

            if cliff_val != "—":
                cliff_html = f"""<div class="cliff-badge">⚠ cliff ~L{cliff_val} &nbsp;·&nbsp; 95% CI {cliff_ci_val}</div>"""
            else:
                cliff_html = '<div class="cliff-badge cliff-none">no cliff detected</div>'

            st.markdown(f"""
            <div style="padding:.65rem 0;border-bottom:1px solid #111">
              <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                <div style="width:9px;height:9px;background:{color};border-radius:50%;flex-shrink:0"></div>
                <div style="font-family:'Antonio';font-size:.82rem;font-weight:700;color:{color};letter-spacing:.1em">{cmpd}</div>
                <div style="margin-left:auto;display:flex;gap:6px;align-items:center">
                  <span style="font-family:'Titillium Web';font-size:.6rem;color:#333">{row['Baseline (s)']:.3f}s</span>
                  <span class="mode-badge" style="color:{mode_color};border:1px solid {mode_color}">{fit_mode} · {n_laps}L</span>
                </div>
              </div>
              {cliff_html}
            </div>
            """, unsafe_allow_html=True)

    st.markdown(f'<div class="sh"><span>Stint Scatter</span> — {driver_code} vs Model Fit</div>', unsafe_allow_html=True)
    fig_scatter = plot_stint_scatter(laps, deg_model, driver=driver_code, save=False)
    if fig_scatter:
        st.pyplot(fig_scatter, use_container_width=True)

    st.markdown('<div class="sh"><span>Phase Slopes</span> — Compound × Phase Breakdown</div>', unsafe_allow_html=True)
    phase_rows = []
    for cmpd in COMPOUNDS:
        ps = deg_model.phase_slopes(cmpd)
        if ps:
            phase_rows.append({"Compound": cmpd, **{k.capitalize(): f"{v:+.4f} s/L" for k,v in ps.items()}})
    if phase_rows:
        st.dataframe(pd.DataFrame(phase_rows), use_container_width=True, hide_index=True)

# ── TAB 4: RESULTS & BACKTEST ────────────────────────────────────
with tab4:
    # 1-stop vs 2-stop summary
    n1 = len(mc_results[mc_results["pit_count"] == 1])
    n2 = len(mc_results[mc_results["pit_count"] == 2])
    b1 = mc_results[mc_results["pit_count"] == 1].iloc[0] if n1 > 0 else None
    b2 = mc_results[mc_results["pit_count"] == 2].iloc[0] if n2 > 0 else None

    if b1 is not None and b2 is not None:
        diff      = b2["mean_time"] - b1["mean_time"]
        w_label   = "1-STOP" if diff > 0 else "2-STOP"
        w_color   = "#e8002d" if diff > 0 else "#ffd700"
        st.markdown(f"""
        <div class="grid2" style="margin-bottom:1rem">
          <div class="gpanel">
            <div class="gpanel-lbl">Best 1-Stop</div>
            <div class="gpanel-val" style="color:#e8002d">{b1['strategy']}</div>
            <div class="gpanel-sub">{b1['mean_time']:.2f}s · {b1['win_rate']:.1%} win · ±{b1['std_time']:.1f}s</div>
          </div>
          <div class="gpanel">
            <div class="gpanel-lbl">Best 2-Stop</div>
            <div class="gpanel-val" style="color:#ffd700">{b2['strategy']}</div>
            <div class="gpanel-sub">{b2['mean_time']:.2f}s · {b2['win_rate']:.1%} win · ±{b2['std_time']:.1f}s</div>
          </div>
        </div>
        <div style="background:var(--off);border:1px solid var(--border);border-left:3px solid {w_color};
                    padding:.8rem 1.4rem;margin-bottom:1.5rem;font-family:'Titillium Web';font-size:.78rem;color:var(--dim)">
          <strong style="color:{w_color}">{w_label}</strong> is faster in expectation by
          <strong style="color:#f5f5f5">{abs(diff):.2f}s</strong>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="sh"><span>Full Results Table</span> — All Strategies Ranked</div>', unsafe_allow_html=True)
    display_cols = ["strategy","mean_time","std_time","p10","p50","p90","pit_count","compounds","win_rate"]
    st.dataframe(
        mc_results[display_cols].style.format({
            "mean_time":"{:.2f}","std_time":"{:.2f}",
            "p10":"{:.2f}","p50":"{:.2f}","p90":"{:.2f}",
            "win_rate":"{:.2%}",
        })
        .bar(subset=["win_rate"], color=["#1a0008","#e8002d"])
        .bar(subset=["mean_time"], color=["#001a00","#1a4a2a"]),
        use_container_width=True, hide_index=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)
    st.download_button(
        "⬇  EXPORT RESULTS CSV",
        data=mc_results[display_cols].to_csv(index=False),
        file_name=f"f1_strategy_{year}_{race}_{driver_code}.csv",
        mime="text/csv",
    )

    # ── BACKTEST ──────────────────────────────────────────────────
    st.markdown('<div class="sh"><span>Backtest</span> — AI Optimal vs Actual Race Strategy</div>', unsafe_allow_html=True)
    try:
        dl = laps_raw[laps_raw["Driver"] == driver_code].copy()
        actual_stints: list[tuple[str,int]] = []
        if "Compound" in dl.columns and "TyreLife" in dl.columns:
            dl = dl.sort_values("LapNumber").reset_index(drop=True)
            dl["_sc"] = (dl["TyreLife"].diff() < 0).cumsum()
            for _, grp in dl.groupby("_sc"):
                cmpd = grp["Compound"].mode()[0] if not grp["Compound"].empty else "HARD"
                dur  = len(grp)
                if dur > 0:
                    actual_stints.append((cmpd, dur))

        if len(actual_stints) >= 2:
            actual_strat  = Strategy(stints=[Stint(c,d) for c,d in actual_stints])
            actual_res    = simulate_race(actual_strat, deg_model, pit_loss, noise_std=0.0)
            optimal_res   = simulate_race(mc_results.iloc[0]["strategy_obj"], deg_model, pit_loss, noise_std=0.0)
            delta_s       = actual_res["total_time"] - optimal_res["total_time"]
            d_sign        = "+" if delta_s > 0 else ""
            d_color       = "#e8002d" if delta_s > 0.5 else ("#39b54a" if delta_s < -0.5 else "#ffd700")
            verdict       = "suboptimal" if delta_s > 0.5 else ("near-optimal" if abs(delta_s) <= 0.5 else "optimal")

            st.markdown(f"""
            <div class="grid3" style="margin-bottom:1rem">
              <div class="gpanel">
                <div class="gpanel-lbl">Actual — {driver_code}</div>
                <div class="gpanel-val">{actual_strat}</div>
                <div class="gpanel-sub">Pit laps: {', '.join(str(l) for l in actual_res['pit_laps']) or 'none recorded'}</div>
              </div>
              <div class="gpanel">
                <div class="gpanel-lbl">AI Optimal</div>
                <div class="gpanel-val" style="color:#e8002d">{mc_results.iloc[0]['strategy']}</div>
                <div class="gpanel-sub">
                  Pit laps: {', '.join(str(l) for l in optimal_res['pit_laps'])}
                  · {mc_results.iloc[0]['win_rate']:.0%} win rate
                </div>
              </div>
              <div class="gpanel" style="border-left:3px solid {d_color}">
                <div class="gpanel-lbl">Delta</div>
                <div style="font-family:'Antonio';font-size:2rem;font-weight:700;color:{d_color};line-height:1">{d_sign}{delta_s:.2f}s</div>
                <div class="gpanel-sub">Actual was <strong style="color:{d_color}">{verdict}</strong></div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            fig_bt = plot_lap_trace(
                [actual_res, optimal_res],
                labels=[f"Actual ({driver_code})", "AI Optimal"],
                save=False,
            )
            st.pyplot(fig_bt, use_container_width=True)
        else:
            st.info("Insufficient stint data to reconstruct the actual strategy for this driver/race.")
    except Exception as e:
        st.warning(f"Backtest unavailable: {e}")

# ── TAB 5: RIVAL ANALYSIS ────────────────────────────────────────
with tab5:
    if session_drivers:
        rival_pool = [k for k in session_drivers if k != driver_code and k in DRIVERS]
        if not rival_pool:
            rival_pool = [k for k in DRIVERS if k != driver_code]
    else:
        rival_pool = [k for k in DRIVERS if k != driver_code]

    st.markdown('<div class="sh"><span>Rival Configuration</span></div>', unsafe_allow_html=True)

    rc1, rc2, rc3 = st.columns(3)
    rival_code     = rc1.selectbox("Rival driver", rival_pool)
    rival_compound = rc2.selectbox("Rival compound", ["SOFT","MEDIUM","HARD"], index=1)
    rival_tyre_age = rc3.slider("Rival tyre age (laps)", 1, 35, 10)

    rival_drv = DRIVERS.get(rival_code, {"color":"#888","num":"?","name":rival_code,"first":"","team":""})

    st.markdown(f"""
    <div class="rival-compare">
      <div>
        <div style="font-family:'Titillium Web';font-size:.56rem;font-weight:700;letter-spacing:.25em;color:#333;text-transform:uppercase;margin-bottom:6px">You</div>
        <div style="display:flex;align-items:center;gap:10px">
          <div style="width:4px;height:44px;background:{drv['color']}"></div>
          <div>
            <div style="font-family:'Antonio';font-size:1.4rem;font-weight:700;color:{drv['color']};line-height:1">{drv['num']}</div>
            <div style="font-family:'Antonio';font-size:.92rem;color:#f5f5f5">{drv['name']}</div>
            <div style="font-family:'Titillium Web';font-size:.58rem;color:#444;letter-spacing:.1em">{drv['team']}</div>
          </div>
        </div>
      </div>
      <div class="rival-vs">VS</div>
      <div>
        <div style="font-family:'Titillium Web';font-size:.56rem;font-weight:700;letter-spacing:.25em;color:#333;text-transform:uppercase;margin-bottom:6px">Rival</div>
        <div style="display:flex;align-items:center;gap:10px">
          <div style="width:4px;height:44px;background:{rival_drv['color']}"></div>
          <div>
            <div style="font-family:'Antonio';font-size:1.4rem;font-weight:700;color:{rival_drv['color']};line-height:1">{rival_drv['num']}</div>
            <div style="font-family:'Antonio';font-size:.92rem;color:#f5f5f5">{rival_drv['name']}</div>
            <div style="font-family:'Titillium Web';font-size:.58rem;color:#444;letter-spacing:.1em">
              {rival_drv['team']}
              &nbsp;·&nbsp;<span style="color:{TYRE_COLORS.get(rival_compound,'#888')}">{rival_compound}</span>
              &nbsp;·&nbsp;L{rival_tyre_age}
            </div>
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    ra1, ra2 = st.columns(2)
    gap_to_rival  = ra1.number_input("Gap to rival (s, + = they lead)", value=2.0, step=0.5)
    scan_from_lap = ra2.slider("Scan window start (lap)", 1, race_total_laps - 10, 15)
    scan_to_lap   = st.slider("Scan window end (lap)", scan_from_lap + 1,
                               race_total_laps - 2, min(scan_from_lap + 15, race_total_laps - 2))

    rb1, rb2 = st.columns(2)
    our_compound_now = rb1.selectbox("Our current compound", ["SOFT","MEDIUM","HARD"], index=1)
    our_tyre_age_now = rb2.slider("Our tyre age (laps)", 1, 35, 10)
    new_compound     = st.selectbox("Compound to fit after pit", ["SOFT","MEDIUM","HARD"], index=2)

    if st.button("▶  RUN RIVAL ANALYSIS", use_container_width=True):
        rival = RivalState(
            driver=rival_code, compound=rival_compound,
            tyre_age=rival_tyre_age, gap_to_us=gap_to_rival,
        )

        with st.spinner("Scanning undercut window…"):
            scan_df = scan_undercut_window(
                from_lap=scan_from_lap, to_lap=scan_to_lap,
                our_compound=our_compound_now,
                our_tyre_age_at_from_lap=our_tyre_age_now,
                new_compound=new_compound,
                rival=rival,
                deg_model=deg_model, pit_loss=pit_loss,
                n_simulations=200, noise_std=noise,
            )

        with st.spinner("Scanning overcut window…"):
            overcut_df = scan_overcut_window(
                from_lap=scan_from_lap, to_lap=scan_to_lap,
                our_compound=our_compound_now,
                our_tyre_age_at_from_lap=our_tyre_age_now,
                new_compound=new_compound,
                rival=rival,
                deg_model=deg_model, pit_loss=pit_loss,
                n_simulations=200, noise_std=noise,
            )

        rec = scan_df[scan_df["recommend"]]
        rec_over = overcut_df[overcut_df["recommend"]]

        best_u_ev = rec["mean_ev"].max() if not rec.empty else -999
        best_o_ev = rec_over["mean_ev"].max() if not rec_over.empty else -999

        if best_u_ev <= -999 and best_o_ev <= -999:
            st.warning("Neither undercut nor overcut shows a clear advantage — consider holding position.")
        else:
            winner       = "UNDERCUT" if best_u_ev >= best_o_ev else "OVERCUT"
            winner_color = "#e8002d" if winner == "UNDERCUT" else "#00d2be"
            winner_ev    = max(best_u_ev, best_o_ev)
            st.markdown(f"""
            <div class="rec-panel" style="border-left-color:{winner_color}">
              <div class="rec-label">AI Recommendation</div>
              <div class="rec-text">
                <span class="strat-pill win" style="background:{winner_color}22;color:{winner_color};border-color:{winner_color}55">
                  {winner}
                </span>
                &nbsp;is the stronger play &nbsp;·&nbsp;
                Best EV: <span class="hl-teal">+{winner_ev:.2f}s</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

        # ── Undercut vs Overcut comparison ────────────────────────────────
        st.markdown('<div class="sh"><span>Undercut vs Overcut</span> — Side-by-Side EV Comparison</div>', unsafe_allow_html=True)
        fig_compare = plot_undercut_vs_overcut(scan_df, overcut_df, rival_driver=rival_code,
                                                our_driver=driver_code, save=False)
        st.pyplot(fig_compare, use_container_width=True)

        uc1, uc2 = st.columns(2)
        with uc1:
            st.markdown(f"""
            <div class="gpanel" style="border-left:3px solid #e8002d">
              <div class="gpanel-lbl">Undercut</div>
              <div class="gpanel-val" style="color:#e8002d">
                {'+' + format(best_u_ev, '.2f') + 's EV' if best_u_ev > -999 else 'No advantage'}
              </div>
              <div class="gpanel-sub">{len(rec)} favourable laps in window</div>
            </div>
            """, unsafe_allow_html=True)
        with uc2:
            st.markdown(f"""
            <div class="gpanel" style="border-left:3px solid #00d2be">
              <div class="gpanel-lbl">Overcut</div>
              <div class="gpanel-val" style="color:#00d2be">
                {'+' + format(best_o_ev, '.2f') + 's EV' if best_o_ev > -999 else 'No advantage'}
              </div>
              <div class="gpanel-sub">{len(rec_over)} favourable laps in window</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<div class="sh"><span>Undercut EV Timeline</span></div>', unsafe_allow_html=True)
        fig_ev = plot_undercut_ev_timeline(scan_df, rival_driver=rival_code,
                                            our_driver=driver_code, mode_label="UNDERCUT", save=False)
        st.pyplot(fig_ev, use_container_width=True)

        st.markdown('<div class="sh"><span>Overcut EV Timeline</span></div>', unsafe_allow_html=True)
        fig_ev_over = plot_undercut_ev_timeline(overcut_df, rival_driver=rival_code,
                                                  our_driver=driver_code, mode_label="OVERCUT", save=False)
        st.pyplot(fig_ev_over, use_container_width=True)

        # Raw scan data
        with st.expander("📋 Raw Scan Data"):
            st.markdown("**Undercut scan**")
            st.dataframe(
                scan_df.style.format({
                    "mean_ev":"{:.3f}","p10_ev":"{:.3f}","p90_ev":"{:.3f}","win_rate":"{:.1%}"
                }),
                use_container_width=True, hide_index=True,
            )
            st.markdown("**Overcut scan**")
            st.dataframe(
                overcut_df.style.format({
                    "mean_ev":"{:.3f}","p10_ev":"{:.3f}","p90_ev":"{:.3f}","win_rate":"{:.1%}"
                }),
                use_container_width=True, hide_index=True,
            )

        # H2H Monte Carlo
        st.markdown(f'<div class="sh"><span>Head-to-Head</span> — Win Rate vs {rival_code}</div>', unsafe_allow_html=True)
        cand = generate_one_stop_strategies(race_total_laps)[:50]

        rival_remaining   = race_total_laps - scan_from_lap
        rival_on_current  = min(rival_remaining, max(5, rival_remaining // 2))
        if rival_remaining > 10:
            alt = "HARD" if rival_compound != "HARD" else "MEDIUM"
            rival_strat = Strategy(stints=[
                Stint(rival_compound, rival_on_current),
                Stint(alt, rival_remaining - rival_on_current),
            ])
        else:
            rival_strat = generate_one_stop_strategies(race_total_laps)[0]

        with st.spinner("Running head-to-head Monte Carlo…"):
            h2h = run_rival_monte_carlo(
                our_strategies=cand[:20], rival_strategy=rival_strat,
                deg_model=deg_model, pit_loss=pit_loss,
                initial_gap=gap_to_rival, n_simulations=150, noise_std=noise,
            )

        fig_h2h = plot_head_to_head_mc(
            {row["strategy"]: row["win_rate"] for _, row in h2h.head(12).iterrows()},
            rival_driver=rival_code, save=False,
        )
        st.pyplot(fig_h2h, use_container_width=True)

        # Best H2H strategy callout
        if not h2h.empty:
            best_h2h = h2h.iloc[0]
            h2h_color = "#39b54a" if best_h2h["win_rate"] >= 0.5 else "#e8002d"
            verdict   = "favourable" if best_h2h["win_rate"] >= 0.5 else "unfavourable"
            st.markdown(f"""
            <div class="rec-panel">
              <div class="rec-label">H2H Summary vs {rival_code}</div>
              <div class="rec-text">
                Best strategy: <span class="hl-red">{best_h2h['strategy']}</span>
                &nbsp;·&nbsp; Win rate: <span style="color:{h2h_color};font-weight:700">{best_h2h['win_rate']:.0%}</span>
                &nbsp;·&nbsp; Matchup is <span style="color:{h2h_color};font-weight:700">{verdict}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

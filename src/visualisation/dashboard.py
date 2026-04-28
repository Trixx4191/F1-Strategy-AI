"""
dashboard.py — F1 Strategy AI · Terminal Edition
Inspired by f1thedata.com — brutalist data-terminal aesthetic
"""

import sys
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from src.pipeline.loader import load_session, get_laps, get_pit_stops
from src.pipeline.cleaner import clean_laps
from src.pipeline.features import engineer_features
from src.models.tyre_deg import TyreDegModel
from src.models.pit_loss import get_pit_loss
from src.simulator.strategy import generate_one_stop_strategies, generate_two_stop_strategies
from src.simulator.monte_carlo import run_monte_carlo
from src.simulator.race_sim import simulate_race
from src.visualisation.tyre_plots import (
    plot_degradation_curves, plot_stint_scatter, plot_compound_comparison_table
)
from src.visualisation.strategy_plots import (
    plot_strategy_comparison, plot_lap_trace, plot_undercut_window
)
from src.simulator.rival import RivalState, scan_undercut_window
from src.simulator.monte_carlo import run_rival_monte_carlo
from src.visualisation.rival_plots import (
    plot_undercut_ev_timeline, plot_gap_trace, plot_head_to_head_mc
)
from src.utils.config import COMPOUNDS, RACE_LAPS, N_SIMULATIONS

# ─────────────────────────────────────────────────────────────────────────────
# DATA REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

DRIVERS = {
    "VER": {"name": "VERSTAPPEN",  "first": "Max",       "team": "RED BULL RACING",  "color": "#3671C6", "num": "1"},
    "PER": {"name": "PÉREZ",       "first": "Sergio",    "team": "RED BULL RACING",  "color": "#3671C6", "num": "11"},
    "LEC": {"name": "LECLERC",     "first": "Charles",   "team": "FERRARI",           "color": "#E8002D", "num": "16"},
    "SAI": {"name": "SAINZ",       "first": "Carlos",    "team": "FERRARI",           "color": "#E8002D", "num": "55"},
    "HAM": {"name": "HAMILTON",    "first": "Lewis",     "team": "MERCEDES",          "color": "#00D2BE", "num": "44"},
    "RUS": {"name": "RUSSELL",     "first": "George",    "team": "MERCEDES",          "color": "#00D2BE", "num": "63"},
    "NOR": {"name": "NORRIS",      "first": "Lando",     "team": "MCLAREN",           "color": "#FF8000", "num": "4"},
    "PIA": {"name": "PIASTRI",     "first": "Oscar",     "team": "MCLAREN",           "color": "#FF8000", "num": "81"},
    "ALO": {"name": "ALONSO",      "first": "Fernando",  "team": "ASTON MARTIN",      "color": "#229971", "num": "14"},
    "STR": {"name": "STROLL",      "first": "Lance",     "team": "ASTON MARTIN",      "color": "#229971", "num": "18"},
    "GAS": {"name": "GASLY",       "first": "Pierre",    "team": "ALPINE",            "color": "#0093CC", "num": "10"},
    "OCO": {"name": "OCON",        "first": "Esteban",   "team": "ALPINE",            "color": "#0093CC", "num": "31"},
    "ALB": {"name": "ALBON",       "first": "Alexander", "team": "WILLIAMS",          "color": "#005AFF", "num": "23"},
    "SAR": {"name": "SARGEANT",    "first": "Logan",     "team": "WILLIAMS",          "color": "#005AFF", "num": "2"},
    "BOT": {"name": "BOTTAS",      "first": "Valtteri",  "team": "KICK SAUBER",       "color": "#52E252", "num": "77"},
    "ZHO": {"name": "ZHOU",        "first": "Guanyu",    "team": "KICK SAUBER",       "color": "#52E252", "num": "24"},
    "HUL": {"name": "HÜLKENBERG",  "first": "Nico",      "team": "HAAS",              "color": "#B6BABD", "num": "27"},
    "MAG": {"name": "MAGNUSSEN",   "first": "Kevin",     "team": "HAAS",              "color": "#B6BABD", "num": "20"},
    "TSU": {"name": "TSUNODA",     "first": "Yuki",      "team": "RB",                "color": "#6692FF", "num": "22"},
    "RIC": {"name": "RICCIARDO",   "first": "Daniel",    "team": "RB",                "color": "#6692FF", "num": "3"},
}

RACES_2024 = [
    "Bahrain","Saudi Arabia","Australia","Japan","China",
    "Miami","Emilia Romagna","Monaco","Canada","Spain",
    "Austria","Great Britain","Hungary","Belgium","Netherlands",
    "Italian","Azerbaijan","Singapore","United States",
    "Mexico City","São Paulo","Las Vegas","Qatar","Abu Dhabi",
]

TYRE_COLORS = {"SOFT": "#E8002D", "MEDIUM": "#FFD700", "HARD": "#F0F2F5", "INTER": "#39B54A", "WET": "#0067FF"}

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────

_VIZ_DIR = Path(__file__).resolve().parent

st.set_page_config(
    page_title="F1 STRATEGY AI",
    page_icon=str(_VIZ_DIR / "f1.png"),
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# BACKGROUND IMAGES (base64-encoded for Streamlit CSS injection)
# ─────────────────────────────────────────────────────────────────────────────

def _b64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

_IMG_RED = _b64(_VIZ_DIR / "F1_RED.jpeg")
_IMG_JACK = _b64(_VIZ_DIR / "JACK TEAM RACING.jpeg")

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL STYLES
# ─────────────────────────────────────────────────────────────────────────────

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Antonio:wght@100;400;700&family=Titillium+Web:ital,wght@0,200;0,300;0,400;0,600;0,700;1,400&display=swap');

/* ── TOKENS ── */
:root {{
  --black:   #000000;
  --off:     #0a0a0a;
  --panel:   #111111;
  --panel2:  #161616;
  --border:  #222222;
  --border2: #2a2a2a;
  --red:     #e8002d;
  --red2:    #ff1a3e;
  --white:   #f5f5f5;
  --dim:     #666666;
  --dim2:    #444444;
  --yellow:  #ffd700;
  --teal:    #00d2be;
  --orange:  #ff8000;

  --font-display: 'Antonio', sans-serif;
  --font-body:    'Titillium Web', sans-serif;
}}

/* ── GLOBAL RESET ── */
*, *::before, *::after {{ box-sizing: border-box; }}

html, body, .stApp {{
  background-color: var(--black);
  background-image: url('data:image/jpeg;base64,{_IMG_RED}'), url('data:image/jpeg;base64,{_IMG_JACK}');
  background-repeat: no-repeat, no-repeat;
  background-position: left center, right center;
  background-size: 50% auto, 50% auto;
  background-attachment: fixed, fixed;
  color: var(--white);
  font-family: var(--font-body);
  scroll-behavior: smooth;
}}

/* Dark overlay so text stays readable over the photos */
.stApp::before {{
  content: '';
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.82);
  z-index: 0;
  pointer-events: none;
}}

/* hide streamlit chrome */
#MainMenu, footer, header {{ visibility: hidden; }}
.stDeployButton {{ display: none; }}
[data-testid="stToolbar"] {{ display: none; }}

/* ── MAIN CONTAINER ── */
.main .block-container {{
  padding: 0 2rem 4rem !important;
  max-width: 1440px !important;
}}

/* ══════════════════════════════
   TOP NAV BAR
══════════════════════════════ */
.f1-nav {{
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--black);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: stretch;
  height: 52px;
  margin: 0 -2rem;
  padding: 0 2rem;
}}
.f1-nav-logo {{
  font-family: var(--font-display);
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: 0.15em;
  color: var(--white);
  display: flex;
  align-items: center;
  gap: 10px;
  padding-right: 2rem;
  border-right: 1px solid var(--border);
  text-transform: uppercase;
  white-space: nowrap;
}}
.f1-nav-logo-dot {{
  width: 8px; height: 8px;
  background: var(--red);
  border-radius: 50%;
  animation: pulse 2s ease-in-out infinite;
}}
@keyframes pulse {{
  0%, 100% {{ opacity: 1; transform: scale(1); }}
  50%       {{ opacity: 0.5; transform: scale(0.8); }}
}}
.f1-nav-items {{
  display: flex;
  align-items: center;
  gap: 0;
  padding: 0 1rem;
  flex: 1;
}}
.f1-nav-item {{
  font-family: var(--font-body);
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.15em;
  color: var(--dim);
  text-transform: uppercase;
  padding: 0 1.1rem;
  height: 52px;
  display: flex;
  align-items: center;
  border-bottom: 2px solid transparent;
  cursor: default;
  transition: color 0.15s, border-color 0.15s;
  white-space: nowrap;
}}
.f1-nav-item:hover {{ color: var(--white); }}
.f1-nav-item.active {{ color: var(--white); border-bottom-color: var(--red); }}
.f1-nav-right {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding-left: 1rem;
  border-left: 1px solid var(--border);
  font-family: var(--font-body);
  font-size: 0.65rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  color: var(--dim);
  text-transform: uppercase;
}}
.f1-live-badge {{
  background: var(--red);
  color: white;
  font-size: 0.55rem;
  font-weight: 700;
  letter-spacing: 0.2em;
  padding: 2px 7px;
  border-radius: 2px;
}}

/* ══════════════════════════════
   SIDEBAR
══════════════════════════════ */
[data-testid="stSidebar"] {{
  background: var(--off) !important;
  border-right: 1px solid var(--border) !important;
  min-width: 280px !important;
  max-width: 280px !important;
}}
[data-testid="stSidebar"] > div:first-child {{
  padding: 0 !important;
}}

.sb-header {{
  padding: 1.4rem 1.25rem 1rem;
  border-bottom: 1px solid var(--border);
  background: var(--black);
}}
.sb-title {{
  font-family: var(--font-display);
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.35em;
  color: var(--dim);
  text-transform: uppercase;
  margin-bottom: 2px;
}}
.sb-subtitle {{
  font-family: var(--font-display);
  font-size: 1.35rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: var(--white);
  text-transform: uppercase;
  line-height: 1.1;
}}
.sb-subtitle span {{ color: var(--red); }}

.sb-section {{
  padding: 0.9rem 1.25rem 0.3rem;
  font-family: var(--font-body);
  font-size: 0.6rem;
  font-weight: 700;
  letter-spacing: 0.3em;
  color: var(--dim2);
  text-transform: uppercase;
  border-top: 1px solid var(--border);
  margin-top: 0.5rem;
}}

/* Driver card */
.drv-card {{
  margin: 0.5rem 1.25rem 0.75rem;
  background: var(--panel);
  border: 1px solid var(--border2);
  display: flex;
  align-items: center;
  gap: 0;
  overflow: hidden;
  transition: border-color 0.25s ease;
  animation: drv-enter 0.35s cubic-bezier(0.22,1,0.36,1);
}}
@keyframes drv-enter {{
  from {{ opacity: 0; transform: translateY(6px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}
.drv-color-bar {{
  width: 4px;
  align-self: stretch;
  flex-shrink: 0;
}}
.drv-num {{
  font-family: var(--font-display);
  font-size: 2rem;
  font-weight: 700;
  color: var(--white);
  padding: 0.75rem 0.75rem 0.75rem 0.85rem;
  line-height: 1;
  opacity: 0.9;
}}
.drv-info {{ flex: 1; padding: 0.75rem 0.75rem 0.75rem 0; }}
.drv-first {{
  font-family: var(--font-body);
  font-size: 0.65rem;
  font-weight: 300;
  color: var(--dim);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  line-height: 1;
}}
.drv-last {{
  font-family: var(--font-display);
  font-size: 1rem;
  font-weight: 700;
  color: var(--white);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  line-height: 1.1;
  margin: 1px 0;
}}
.drv-team {{
  font-family: var(--font-body);
  font-size: 0.58rem;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--dim);
  text-transform: uppercase;
}}

/* ── SIDEBAR CONTROLS ── */
.stSelectbox label, .stSlider label, .stRadio label, .stNumberInput label {{
  font-family: var(--font-body) !important;
  font-size: 0.62rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.2em !important;
  color: var(--dim) !important;
  text-transform: uppercase !important;
}}
[data-baseweb="select"] > div {{
  background: var(--panel) !important;
  border: 1px solid var(--border2) !important;
  border-radius: 0 !important;
  color: var(--white) !important;
  font-family: var(--font-body) !important;
  font-size: 0.85rem !important;
  font-weight: 600 !important;
}}
[data-baseweb="select"] > div:focus-within {{
  border-color: var(--red) !important;
  box-shadow: none !important;
}}
.stSlider [data-baseweb="slider"] {{
  padding: 0 !important;
}}
.stSlider [data-baseweb="slider"] [role="slider"] {{
  background: var(--red) !important;
  border-color: var(--red) !important;
  width: 14px !important; height: 14px !important;
}}
.stSlider [data-baseweb="slider"] div:nth-child(2) > div:nth-child(2) {{
  background: var(--red) !important;
}}
.stRadio [data-baseweb="radio"] > label {{
  gap: 8px !important;
  font-family: var(--font-body) !important;
  font-size: 0.78rem !important;
  font-weight: 600 !important;
  color: var(--white) !important;
}}
.stRadio [data-baseweb="radio"] [type="radio"]:checked + div {{
  border-color: var(--red) !important;
  background: var(--red) !important;
}}

/* RUN BUTTON */
.stButton > button[kind="primary"] {{
  background: var(--red) !important;
  border: none !important;
  border-radius: 0 !important;
  font-family: var(--font-display) !important;
  font-size: 0.8rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.3em !important;
  color: white !important;
  padding: 0.85rem 1.5rem !important;
  width: 100% !important;
  transition: background 0.15s, letter-spacing 0.2s !important;
  text-transform: uppercase !important;
}}
.stButton > button[kind="primary"]:hover {{
  background: var(--red2) !important;
  letter-spacing: 0.4em !important;
}}
.stButton > button:not([kind="primary"]) {{
  background: var(--panel) !important;
  border: 1px solid var(--border2) !important;
  border-radius: 0 !important;
  font-family: var(--font-body) !important;
  font-size: 0.72rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.15em !important;
  color: var(--white) !important;
  padding: 0.65rem 1.5rem !important;
  width: 100% !important;
  transition: border-color 0.15s !important;
}}
.stButton > button:not([kind="primary"]):hover {{
  border-color: var(--red) !important;
}}

/* ══════════════════════════════
   MAIN CONTENT
══════════════════════════════ */

/* ── HERO SECTION ── */
.hero-section {{
  padding: 3rem 0 2.5rem;
  border-bottom: 1px solid var(--border);
  position: relative;
  overflow: hidden;
}}
.hero-eyebrow {{
  font-family: var(--font-body);
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.35em;
  color: var(--red);
  text-transform: uppercase;
  margin-bottom: 0.75rem;
  display: flex;
  align-items: center;
  gap: 10px;
}}
.hero-eyebrow::before {{
  content: '';
  width: 24px; height: 1px;
  background: var(--red);
}}
.hero-h1 {{
  font-family: var(--font-display);
  font-size: clamp(2.8rem, 6vw, 5.5rem);
  font-weight: 700;
  line-height: 0.9;
  text-transform: uppercase;
  letter-spacing: -0.02em;
  color: var(--white);
  margin-bottom: 0.5rem;
}}
.hero-h1 em {{
  color: var(--red);
  font-style: normal;
}}
.hero-meta {{
  font-family: var(--font-body);
  font-size: 0.75rem;
  font-weight: 400;
  letter-spacing: 0.15em;
  color: var(--dim);
  text-transform: uppercase;
  margin-top: 1.2rem;
}}
.hero-meta strong {{ color: var(--white); font-weight: 600; }}

/* Decorative circuit lines */
.hero-circuit {{
  position: absolute;
  right: -40px; top: 50%;
  transform: translateY(-50%);
  opacity: 0.07;
  pointer-events: none;
}}

/* F1 car silhouette */
.f1-car-hero {{
  position: absolute;
  right: 2rem;
  bottom: -12px;
  opacity: 0.06;
  pointer-events: none;
  animation: car-idle 4s ease-in-out infinite;
}}
@keyframes car-idle {{
  0%, 100% {{ transform: translateY(0px); }}
  50%       {{ transform: translateY(-4px); }}
}}

/* ── METRIC STRIP ── */
.metric-strip {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border-bottom: 1px solid var(--border);
  animation: strip-in 0.5s ease-out;
}}
@keyframes strip-in {{
  from {{ opacity: 0; transform: translateY(-8px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}
.metric-cell {{
  padding: 1.6rem 1.8rem;
  border-right: 1px solid var(--border);
  position: relative;
  transition: background 0.2s;
}}
.metric-cell:last-child {{ border-right: none; }}
.metric-cell:hover {{ background: var(--panel); }}
.metric-cell::before {{
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: var(--red);
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.3s ease;
}}
.metric-cell:hover::before {{ transform: scaleX(1); }}
.mc-label {{
  font-family: var(--font-body);
  font-size: 0.58rem;
  font-weight: 700;
  letter-spacing: 0.3em;
  color: var(--dim);
  text-transform: uppercase;
  margin-bottom: 0.5rem;
}}
.mc-value {{
  font-family: var(--font-display);
  font-size: 2.2rem;
  font-weight: 700;
  color: var(--white);
  line-height: 1;
  letter-spacing: -0.02em;
}}
.mc-value.accent-red  {{ color: var(--red); }}
.mc-value.accent-teal {{ color: var(--teal); }}
.mc-value.accent-gold {{ color: var(--yellow); }}
.mc-value.accent-orange {{ color: var(--orange); }}
.mc-unit {{
  font-family: var(--font-body);
  font-size: 0.7rem;
  color: var(--dim);
  font-weight: 400;
  margin-left: 2px;
}}
.mc-sub {{
  font-family: var(--font-body);
  font-size: 0.65rem;
  color: var(--dim);
  margin-top: 4px;
  letter-spacing: 0.05em;
}}

/* ── TABS ── */
.stTabs [data-baseweb="tab-list"] {{
  background: var(--black) !important;
  border-bottom: 1px solid var(--border) !important;
  gap: 0 !important;
  padding: 0 !important;
  overflow-x: auto;
}}
.stTabs [data-baseweb="tab"] {{
  background: transparent !important;
  color: var(--dim) !important;
  font-family: var(--font-body) !important;
  font-size: 0.68rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.2em !important;
  text-transform: uppercase !important;
  padding: 1rem 1.6rem !important;
  border: none !important;
  border-bottom: 2px solid transparent !important;
  border-radius: 0 !important;
  transition: color 0.15s, border-color 0.15s !important;
  white-space: nowrap !important;
}}
.stTabs [data-baseweb="tab"]:hover {{
  color: var(--white) !important;
  background: var(--panel) !important;
}}
.stTabs [aria-selected="true"] {{
  color: var(--white) !important;
  border-bottom-color: var(--red) !important;
  background: transparent !important;
}}
.stTabs [data-baseweb="tab-panel"] {{
  padding: 2rem 0 0 !important;
}}
.stTabs [data-baseweb="tab-highlight"] {{ display: none !important; }}

/* ── SECTION HEADERS ── */
.sec-head {{
  font-family: var(--font-display);
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.35em;
  color: var(--dim);
  text-transform: uppercase;
  margin: 2rem 0 1rem;
  display: flex;
  align-items: center;
  gap: 14px;
}}
.sec-head::after {{
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}}
.sec-head span {{
  color: var(--white);
}}

/* ── DATA TABLE ── */
.stDataFrame {{
  border: 1px solid var(--border) !important;
  border-radius: 0 !important;
}}
.stDataFrame table {{
  font-family: var(--font-body) !important;
  font-size: 0.78rem !important;
  border-collapse: collapse !important;
}}
.stDataFrame thead th {{
  background: var(--panel) !important;
  color: var(--dim) !important;
  font-size: 0.6rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.2em !important;
  text-transform: uppercase !important;
  border-bottom: 1px solid var(--border) !important;
  padding: 0.6rem 0.8rem !important;
}}
.stDataFrame tbody tr:hover td {{
  background: var(--panel) !important;
}}

/* ── ALERTS ── */
.stAlert {{
  background: var(--panel) !important;
  border: 1px solid var(--border2) !important;
  border-left: 2px solid var(--red) !important;
  border-radius: 0 !important;
  font-family: var(--font-body) !important;
  font-size: 0.8rem !important;
}}

/* ── SPINNER ── */
.stSpinner > div {{ border-top-color: var(--red) !important; }}

/* ── DIVIDER ── */
hr {{ border-color: var(--border) !important; margin: 1.5rem 0 !important; }}

/* ── SCROLLBAR ── */
::-webkit-scrollbar {{ width: 4px; height: 4px; }}
::-webkit-scrollbar-track {{ background: var(--black); }}
::-webkit-scrollbar-thumb {{ background: var(--border2); }}
::-webkit-scrollbar-thumb:hover {{ background: var(--red); }}

/* ── DOWNLOAD BUTTON ── */
.stDownloadButton button {{
  background: transparent !important;
  border: 1px solid var(--border2) !important;
  border-radius: 0 !important;
  font-family: var(--font-body) !important;
  font-size: 0.68rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.2em !important;
  color: var(--white) !important;
  padding: 0.6rem 1.5rem !important;
  transition: border-color 0.15s, background 0.15s !important;
}}
.stDownloadButton button:hover {{
  border-color: var(--red) !important;
  background: rgba(232,0,45,0.07) !important;
}}

/* ── NUMBER INPUT ── */
.stNumberInput input {{
  background: var(--panel) !important;
  border: 1px solid var(--border2) !important;
  border-radius: 0 !important;
  color: var(--white) !important;
  font-family: var(--font-body) !important;
  font-size: 0.85rem !important;
}}

/* TYRE PILL */
.tyre-pill {{
  display: inline-block;
  font-family: var(--font-display);
  font-size: 0.55rem;
  font-weight: 700;
  letter-spacing: 0.2em;
  padding: 2px 8px;
  border-radius: 1px;
  text-transform: uppercase;
}}

/* SUCCESS BANNER */
.success-bar {{
  background: rgba(232,0,45,0.06);
  border: 1px solid rgba(232,0,45,0.2);
  border-left: 2px solid var(--red);
  padding: 0.9rem 1.4rem;
  font-family: var(--font-body);
  font-size: 0.78rem;
  color: var(--dim);
  letter-spacing: 0.05em;
  margin-bottom: 0;
  animation: bar-in 0.4s ease-out;
}}
@keyframes bar-in {{
  from {{ opacity: 0; }}
  to   {{ opacity: 1; }}
}}
.success-bar strong {{ color: var(--white); }}

/* Recommendation panel */
.rec-panel {{
  background: var(--panel);
  border: 1px solid var(--border2);
  border-left: 3px solid var(--yellow);
  padding: 1.2rem 1.6rem;
  margin: 1rem 0 1.5rem;
  animation: drv-enter 0.4s ease-out;
}}
.rec-label {{
  font-family: var(--font-body);
  font-size: 0.58rem;
  font-weight: 700;
  letter-spacing: 0.3em;
  color: var(--dim);
  text-transform: uppercase;
  margin-bottom: 0.5rem;

  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 1rem;
  padding: 1.5rem 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 1.5rem;
}}
.rival-vs {{
  font-family: var(--font-display);
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--dim2);
  text-align: center;
}}

/* Landing state */
.landing-grid {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  margin: 3rem 0 2rem;
  animation: fadeIn 0.7s ease-out;
}}
@keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
.landing-cell {{
  background: var(--black);
  padding: 2.5rem 2rem;
  transition: background 0.2s;
}}
.landing-cell:hover {{ background: var(--panel); }}
.landing-num {{
  font-family: var(--font-display);
  font-size: 3.5rem;
  font-weight: 700;
  line-height: 1;
  margin-bottom: 0.5rem;
}}
.landing-desc {{
  font-family: var(--font-body);
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.25em;
  color: var(--dim);
  text-transform: uppercase;
}}
.landing-cta {{
  background: var(--panel);
  border: 1px solid var(--border2);
  border-left: 2px solid var(--dim2);
  padding: 1.2rem 1.6rem;
  font-family: var(--font-body);
  font-size: 0.82rem;
  color: var(--dim);
  animation: fadeIn 1s ease-out;
}}

</style>
"""

st.markdown(_CSS.format(_IMG_RED=_IMG_RED, _IMG_JACK=_IMG_JACK), unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="sb-header">
        <div class="sb-title">Monte Carlo Engine</div>
        <div class="sb-subtitle">F1 <span>Strategy</span><br>Intelligence</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sb-section">Session</div>', unsafe_allow_html=True)
    year = st.selectbox("SEASON", [2024, 2023, 2022], index=0, label_visibility="collapsed")
    race = st.selectbox("GRAND PRIX", RACES_2024, index=0)

    st.markdown('<div class="sb-section">Driver</div>', unsafe_allow_html=True)
    driver_code = st.selectbox("SELECT DRIVER", list(DRIVERS.keys()), index=0)
    drv = DRIVERS[driver_code]
    st.markdown(f"""
    <div class="drv-card">
        <div class="drv-color-bar" style="background:{drv['color']}"></div>
        <div class="drv-num">{drv['num']}</div>
        <div class="drv-info">
            <div class="drv-first">{drv['first']}</div>
            <div class="drv-last">{drv['name']}</div>
            <div class="drv-team" style="color:{drv['color']}">{drv['team']}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sb-section">Simulation</div>', unsafe_allow_html=True)
    n_sims = st.slider("MC ITERATIONS", 100, 2000, N_SIMULATIONS, step=100)
    stop_strategy = st.radio("STRATEGY TYPE", ["1-stop", "2-stop", "Both"])
    noise = st.slider("LAP TIME NOISE (s)", 0.0, 1.0, 0.3, step=0.05)

    st.markdown("<br>", unsafe_allow_html=True)
    run_btn = st.button("▶  RUN SIMULATION", use_container_width=True, type="primary")
    st.markdown("<br>", unsafe_allow_html=True)

    # Sidebar footer
    st.markdown(f"""
    <div style="padding:1rem 1.25rem;border-top:1px solid var(--border,#222);
                font-family:'Titillium Web',sans-serif;font-size:0.58rem;
                font-weight:600;letter-spacing:0.15em;color:#444;text-transform:uppercase">
        {year} SEASON · {race.upper()} GP<br>
        <span style="color:#222;margin-top:4px;display:block">POWERED BY FASTF1</span>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# TOP NAV
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="f1-nav">
    <div class="f1-nav-logo">
        <div class="f1-nav-logo-dot"></div>
        F1 Strategy AI
    </div>
    <div class="f1-nav-items">
        <div class="f1-nav-item active">Strategy</div>
        <div class="f1-nav-item">Tyre Model</div>
        <div class="f1-nav-item">Rival Analysis</div>
        <div class="f1-nav-item">Lap Times</div>
        <div class="f1-nav-item">Pit Stops</div>
    </div>
    <div class="f1-nav-right">
        <span class="f1-live-badge">AI</span>
        {year} · {race}
    </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# HERO
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="hero-section">
    <!-- Decorative F1 car silhouette -->
    <div class="f1-car-hero">
        <svg width="640" height="140" viewBox="0 0 640 140" fill="white" xmlns="http://www.w3.org/2000/svg">
            <ellipse cx="320" cy="82" rx="260" ry="24" fill="white"/>
            <polygon points="555,82 625,79 625,85" fill="white"/>
            <ellipse cx="312" cy="60" rx="68" ry="22" fill="white"/>
            <rect x="279" y="44" width="64" height="6" rx="2" fill="white"/>
            <rect x="279" y="44" width="6" height="28" rx="2" fill="white"/>
            <rect x="337" y="44" width="6" height="28" rx="2" fill="white"/>
            <rect x="496" y="98" width="112" height="8" rx="1" fill="white"/>
            <rect x="489" y="84" width="8" height="24" rx="1" fill="white"/>
            <rect x="606" y="86" width="16" height="5" rx="1" fill="white"/>
            <rect x="606" y="100" width="16" height="5" rx="1" fill="white"/>
            <rect x="48" y="42" width="96" height="10" rx="1" fill="white"/>
            <rect x="72" y="52" width="48" height="5" rx="1" fill="white"/>
            <rect x="48" y="42" width="6" height="36" rx="1" fill="white"/>
            <rect x="138" y="42" width="6" height="36" rx="1" fill="white"/>
            <ellipse cx="488" cy="110" rx="22" ry="22" fill="white"/>
            <ellipse cx="488" cy="110" rx="13" ry="13" fill="black"/>
            <ellipse cx="144" cy="112" rx="27" ry="27" fill="white"/>
            <ellipse cx="144" cy="112" rx="16" ry="16" fill="black"/>


        <strong style="color:{drv['color']}">{drv['first']} {drv['name']}</strong> &nbsp;·&nbsp;
        {drv['team']}
    </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# LANDING STATE
# ─────────────────────────────────────────────────────────────────────────────
if not run_btn:
    st.markdown("""
    <div class="landing-grid">
        <div class="landing-cell">
            <div class="landing-num" style="color:#e8002d">252</div>
            <div class="landing-desc">Strategies Evaluated</div>
        </div>
        <div class="landing-cell">
            <div class="landing-num" style="color:#ffd700">1000</div>
            <div class="landing-desc">Monte Carlo Iterations</div>
        </div>
        <div class="landing-cell">
            <div class="landing-num" style="color:#00d2be">20</div>
            <div class="landing-desc">Driver Profiles</div>
        </div>
        <div class="landing-cell">
            <div class="landing-num" style="color:#ff8000">2</div>
            <div class="landing-desc">Strategy Types</div>
        </div>
        <div class="landing-cell">
            <div class="landing-num" style="color:#6692ff">3</div>
            <div class="landing-desc">Tyre Compounds</div>
        </div>
        <div class="landing-cell">
            <div class="landing-num" style="color:#52e252">&lt;15s</div>
            <div class="landing-desc">Full Simulation Time</div>
        </div>
    </div>
    <div class="landing-cta">
        Configure your session in the sidebar — select season, race, driver and simulation parameters —
        then press <strong style="color:#f5f5f5">RUN SIMULATION</strong> to begin the analysis.
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# MATPLOTLIB THEME
# ─────────────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor":  "#000000",
    "axes.facecolor":    "#0a0a0a",
    "axes.edgecolor":    "#222222",
    "axes.labelcolor":   "#666666",
    "axes.labelsize":    8,
    "axes.titlesize":    9,
    "axes.titlecolor":   "#f5f5f5",
    "xtick.color":       "#444444",
    "ytick.color":       "#444444",
    "xtick.labelsize":   7,
    "ytick.labelsize":   7,
    "text.color":        "#f5f5f5",
    "grid.color":        "#1a1a1a",
    "grid.linestyle":    "-",
    "grid.linewidth":    0.5,
    "legend.facecolor":  "#111111",
    "legend.edgecolor":  "#222222",
    "legend.fontsize":   7,
    "font.family":       ["Titillium Web", "monospace"],
    "figure.dpi":        130,
})

# ─────────────────────────────────────────────────────────────────────────────
# DATA PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
with st.spinner("Loading FastF1 session data…"):
    try:
        session   = load_session(year, race)
        laps_raw  = get_laps(session)
        pit_stops = get_pit_stops(session)
    except Exception as e:
        st.error(f"Failed to load session: {e}")
        st.stop()

with st.spinner("Cleaning & feature engineering…"):
    laps = clean_laps(laps_raw)
    laps = engineer_features(laps, total_laps=RACE_LAPS)

with st.spinner("Fitting tyre degradation model…"):
    deg_model = TyreDegModel()
    deg_model.fit(laps)
    pit_loss = get_pit_loss(pit_stops)

with st.spinner(f"Running {n_sims:,} Monte Carlo simulations…"):
    strategies = []
    if stop_strategy in ["1-stop", "Both"]:
        strategies += generate_one_stop_strategies(RACE_LAPS)
    if stop_strategy in ["2-stop", "Both"]:
        strategies += generate_two_stop_strategies(RACE_LAPS)

    mc_results = run_monte_carlo(
        strategies, deg_model, pit_loss,
        n_simulations=n_sims, noise_std=noise
    )

# ─────────────────────────────────────────────────────────────────────────────
# SUCCESS BAR
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="success-bar">
    ✓ &nbsp; Simulation complete —
    <strong>{len(strategies):,} strategies</strong> evaluated across
    <strong>{n_sims:,} Monte Carlo iterations</strong> &nbsp;·&nbsp;
    Best: <strong>{mc_results.iloc[0]['strategy']}</strong>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# METRIC STRIP
# ─────────────────────────────────────────────────────────────────────────────
best = mc_results.iloc[0]
worst = mc_results.iloc[-1]
delta = worst["mean_time"] - best["mean_time"]

st.markdown(f"""
<div class="metric-strip">
    <div class="metric-cell">
        <div class="mc-label">Optimal Strategy</div>
        <div class="mc-value accent-red" style="font-size:1.3rem;margin-top:4px">{best['strategy']}</div>
        <div class="mc-sub">{best['pit_count']}-stop · {best['compounds']}</div>
    </div>
    <div class="metric-cell">
        <div class="mc-label">Mean Race Time</div>
        <div class="mc-value">{best['mean_time']:.1f}<span class="mc-unit">s</span></div>
        <div class="mc-sub">± {best['std_time']:.1f}s uncertainty</div>
    </div>
    <div class="metric-cell">
        <div class="mc-label">Time vs Worst</div>
        <div class="mc-value accent-teal">+{delta:.1f}<span class="mc-unit">s</span></div>
        <div class="mc-sub">advantage over worst strategy</div>
    </div>
    <div class="metric-cell">
        <div class="mc-label">Win Rate</div>
        <div class="mc-value accent-gold">{best['win_rate']:.1%}</div>
        <div class="mc-sub">probability of optimal outcome</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Strategy Comparison",
    "Undercut Window",
    "Tyre Model",
    "Full Results",
    "Rival Analysis",
])

# ── TAB 1: STRATEGY COMPARISON ────────────────────────────────────────────────
with tab1:
    c1, c2 = st.columns([3, 1])

    with c1:
        st.markdown('<div class="sec-head"><span>Top Strategies</span> — Mean Race Time Delta</div>', unsafe_allow_html=True)
        fig = plot_strategy_comparison(mc_results, top_n=15, save=False)
        st.pyplot(fig, use_container_width=True)

    with c2:
        st.markdown('<div class="sec-head"><span>Top 5</span></div>', unsafe_allow_html=True)
        for i, row in mc_results.head(5).iterrows():
            rank_color = ["#FFD700","#C0C0C0","#CD7F32","#666","#444"][i]
            st.markdown(f"""
            <div style="border:1px solid #1a1a1a;border-left:3px solid {rank_color};
                        padding:0.8rem 1rem;margin-bottom:0.5rem;background:#0a0a0a;
                        transition:background 0.2s">
                <div style="font-family:'Titillium Web';font-size:0.58rem;letter-spacing:0.2em;
                            color:#444;text-transform:uppercase;margin-bottom:2px">#{i+1}</div>
                <div style="font-family:'Antonio';font-size:0.85rem;font-weight:700;
                            color:#f5f5f5;letter-spacing:0.05em">{row['strategy']}</div>
                <div style="font-family:'Titillium Web';font-size:0.65rem;color:#666;margin-top:3px">
                    {row['mean_time']:.2f}s &nbsp;·&nbsp; {row['win_rate']:.1%} win
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown('<div class="sec-head"><span>Lap-by-Lap Trace</span> — Top 3 Strategies</div>', unsafe_allow_html=True)
    top3   = mc_results.head(3)
    traces = [simulate_race(row["strategy_obj"], deg_model, pit_loss, noise_std=0.0) for _, row in top3.iterrows()]
    fig2   = plot_lap_trace(traces, labels=list(top3["strategy"]), save=False)
    st.pyplot(fig2, use_container_width=True)

# ── TAB 2: UNDERCUT ───────────────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="sec-head"><span>Undercut Window</span> — Optimal Pit Lap Heatmap</div>', unsafe_allow_html=True)
    fig3 = plot_undercut_window(mc_results, RACE_LAPS, save=False)
    if fig3:
        st.pyplot(fig3, use_container_width=True)
    else:
        st.warning("No one-stop strategies found for this race configuration.")

# ── TAB 3: TYRE MODEL ─────────────────────────────────────────────────────────
with tab3:
    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.markdown('<div class="sec-head"><span>Degradation Curves</span> — All Compounds</div>', unsafe_allow_html=True)
        fig4 = plot_degradation_curves(deg_model, save=False)
        st.pyplot(fig4, use_container_width=True)
    with col_b:
        st.markdown('<div class="sec-head"><span>Model Summary</span></div>', unsafe_allow_html=True)
        sumdf = deg_model.summary()
        st.dataframe(sumdf, use_container_width=True, hide_index=True)

        st.markdown('<br>', unsafe_allow_html=True)
        st.markdown('<div class="sec-head"><span>Tyre Palette</span></div>', unsafe_allow_html=True)
        for _, row in sumdf.iterrows():
            cmpd  = row["Compound"]
            color = TYRE_COLORS.get(cmpd, "#888")
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:10px;padding:0.5rem 0;
                        border-bottom:1px solid #1a1a1a">
                <div style="width:10px;height:10px;background:{color};border-radius:50%;flex-shrink:0"></div>
                <div style="font-family:'Antonio';font-size:0.8rem;font-weight:700;
                            color:{color};letter-spacing:0.1em">{cmpd}</div>
                <div style="font-family:'Titillium Web';font-size:0.65rem;color:#444;margin-left:auto">
                    {row['Baseline (s)']:.3f}s baseline
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown(f'<div class="sec-head"><span>Stint Scatter</span> — {driver_code} vs Model Fit</div>', unsafe_allow_html=True)
    fig5 = plot_stint_scatter(laps, deg_model, driver=driver_code, save=False)
    st.pyplot(fig5, use_container_width=True)

# ── TAB 4: FULL RESULTS ───────────────────────────────────────────────────────
with tab4:
    # Quick stats row
    n_one   = len(mc_results[mc_results["pit_count"] == 1])
    n_two   = len(mc_results[mc_results["pit_count"] == 2])
    best_1s = mc_results[mc_results["pit_count"] == 1].iloc[0] if n_one > 0 else None
    best_2s = mc_results[mc_results["pit_count"] == 2].iloc[0] if n_two > 0 else None

    if best_1s is not None and best_2s is not None:
        diff = best_2s["mean_time"] - best_1s["mean_time"]
        winner = "1-STOP" if diff > 0 else "2-STOP"
        winner_color = "#e8002d" if diff > 0 else "#ffd700"
        st.markdown(f"""
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#1a1a1a;
                    border:1px solid #1a1a1a;margin-bottom:1.5rem">
            <div style="background:#0a0a0a;padding:1.2rem 1.6rem">
                <div style="font-family:'Titillium Web';font-size:0.58rem;font-weight:700;
                            letter-spacing:0.3em;color:#666;text-transform:uppercase;margin-bottom:4px">
                    Best 1-Stop
                </div>
                <div style="font-family:'Antonio';font-size:1.3rem;font-weight:700;color:#e8002d">
                    {best_1s['strategy']}
                </div>
                <div style="font-family:'Titillium Web';font-size:0.7rem;color:#444;margin-top:2px">
                    {best_1s['mean_time']:.2f}s · {best_1s['win_rate']:.1%} win rate
                </div>
            </div>
            <div style="background:#0a0a0a;padding:1.2rem 1.6rem">
                <div style="font-family:'Titillium Web';font-size:0.58rem;font-weight:700;
                            letter-spacing:0.3em;color:#666;text-transform:uppercase;margin-bottom:4px">
                    Best 2-Stop
                </div>
                <div style="font-family:'Antonio';font-size:1.3rem;font-weight:700;color:#ffd700">
                    {best_2s['strategy']}
                </div>
                <div style="font-family:'Titillium Web';font-size:0.7rem;color:#444;margin-top:2px">
                    {best_2s['mean_time']:.2f}s · {best_2s['win_rate']:.1%} win rate
                </div>
            </div>
        </div>
        <div style="background:#0a0a0a;border:1px solid #1a1a1a;border-left:3px solid {winner_color};
                    padding:0.8rem 1.4rem;margin-bottom:1.5rem;font-family:'Titillium Web';
                    font-size:0.78rem;color:#666">
            <strong style="color:{winner_color}">{winner}</strong> is faster by
            <strong style="color:#f5f5f5">{abs(diff):.2f}s</strong> in expectation
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="sec-head"><span>Monte Carlo Results</span> — All Strategies</div>', unsafe_allow_html=True)
    display_cols = ["strategy","mean_time","std_time","p10","p50","p90","pit_count","compounds","win_rate"]
    st.dataframe(
        mc_results[display_cols].style.format({
            "mean_time":"{:.2f}","std_time":"{:.2f}",
            "p10":"{:.2f}","p50":"{:.2f}","p90":"{:.2f}",
            "win_rate":"{:.2%}",
        }).bar(subset=["win_rate"], color=["#1a0008","#e8002d"])
         .bar(subset=["mean_time"], color=["#001a00","#229971"]),
        use_container_width=True, hide_index=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)
    st.download_button(
        "⬇  EXPORT RESULTS CSV",
        data=mc_results[display_cols].to_csv(index=False),
        file_name=f"f1_strategy_{year}_{race}_{driver_code}.csv",
        mime="text/csv",
    )

# ── TAB 5: RIVAL ANALYSIS ─────────────────────────────────────────────────────
with tab5:
    rival_drivers = [k for k in DRIVERS if k != driver_code]

    st.markdown('<div class="sec-head"><span>Rival Configuration</span></div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    rival_code     = c1.selectbox("Rival driver", rival_drivers)
    rival_compound = c2.selectbox("Rival compound", ["SOFT","MEDIUM","HARD"], index=1)
    rival_tyre_age = c3.slider("Rival tyre age (laps)", 1, 35, 10)

    rival_drv = DRIVERS[rival_code]

    # Visual head-to-head comparison
    st.markdown(f"""
    <div class="rival-compare">
        <div>
            <div style="font-family:'Titillium Web';font-size:0.58rem;font-weight:700;
                        letter-spacing:0.3em;color:#444;text-transform:uppercase;margin-bottom:6px">You</div>
            <div style="display:flex;align-items:center;gap:10px">
                <div style="width:4px;height:40px;background:{drv['color']}"></div>
                <div>
                    <div style="font-family:'Antonio';font-size:1.4rem;font-weight:700;
                                color:{drv['color']};line-height:1">{drv['num']}</div>
                    <div style="font-family:'Antonio';font-size:0.9rem;color:#f5f5f5">{drv['name']}</div>
                    <div style="font-family:'Titillium Web';font-size:0.6rem;color:#444;
                                letter-spacing:0.1em">{drv['team']}</div>
                </div>
            </div>
        </div>
        <div class="rival-vs">VS</div>
        <div>
            <div style="font-family:'Titillium Web';font-size:0.58rem;font-weight:700;
                        letter-spacing:0.3em;color:#444;text-transform:uppercase;margin-bottom:6px">Rival</div>
            <div style="display:flex;align-items:center;gap:10px">
                <div style="width:4px;height:40px;background:{rival_drv['color']}"></div>
                <div>
                    <div style="font-family:'Antonio';font-size:1.4rem;font-weight:700;
                                color:{rival_drv['color']};line-height:1">{rival_drv['num']}</div>
                    <div style="font-family:'Antonio';font-size:0.9rem;color:#f5f5f5">{rival_drv['name']}</div>
                    <div style="font-family:'Titillium Web';font-size:0.6rem;color:#444;
                                letter-spacing:0.1em">{rival_drv['team']} ·
                        <span style="color:{TYRE_COLORS.get(rival_compound,'#888')}">{rival_compound}</span>
                        · Lap {rival_tyre_age}
                    </div>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    c4, c5 = st.columns(2)
    gap_to_rival  = c4.number_input("Gap to rival (s, + = they lead)", value=2.0, step=0.5)
    scan_from_lap = c5.slider("Scan window start (lap)", 1, 40, 15)
    scan_to_lap   = st.slider("Scan window end (lap)", scan_from_lap + 1, 55, min(scan_from_lap + 15, 40))
    new_compound  = st.selectbox("Compound to fit on our pit", ["SOFT","MEDIUM","HARD"], index=1)

    if st.button("▶  RUN RIVAL ANALYSIS", use_container_width=True):
        rival = RivalState(
            driver=rival_code,
            compound=rival_compound,
            tyre_age=rival_tyre_age,
            gap_to_us=gap_to_rival,
        )

        with st.spinner("Scanning undercut window…"):
            scan_df = scan_undercut_window(
                from_lap=scan_from_lap, to_lap=scan_to_lap,
                our_compound=rival_compound,
                our_tyre_age_at_from_lap=rival_tyre_age,
                new_compound=new_compound,
                rival=rival,
                deg_model=deg_model, pit_loss=pit_loss,
                n_simulations=200, noise_std=noise,
            )

        recommended = scan_df[scan_df["recommend"]]
        if not recommended.empty:
            best_lap = recommended.iloc[recommended["mean_ev"].argmax()]
            st.markdown(f"""
            <div class="rec-panel">
                <div class="rec-label">AI Recommendation</div>
                <div class="rec-text">
                    Pit window: Laps <span class="hl-red">{recommended['lap'].min()}–{recommended['lap'].max()}</span>
                    &nbsp;·&nbsp; Best lap:
                    <span class="hl-red">{int(best_lap['lap'])}</span>
                    &nbsp;·&nbsp; Expected gain:
                    <span class="hl">+{best_lap['mean_ev']:.2f}s</span>
                    &nbsp;·&nbsp; Win rate:
                    <span class="hl-teal">{best_lap['win_rate']:.0%}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.warning("No undercut window found — overcut or hold position recommended.")

        st.markdown('<div class="sec-head"><span>Undercut EV Timeline</span></div>', unsafe_allow_html=True)
        fig_ev = plot_undercut_ev_timeline(scan_df, rival_driver=rival_code, our_driver=driver_code, save=False)
        st.pyplot(fig_ev, use_container_width=True)

        st.markdown(f'<div class="sec-head"><span>Head-to-Head</span> — Win Rate vs {rival_code}</div>', unsafe_allow_html=True)
        cand = generate_one_stop_strategies(RACE_LAPS)[:50]
        rival_strat = generate_one_stop_strategies(RACE_LAPS)[0]

        with st.spinner("Running head-to-head Monte Carlo…"):
            h2h = run_rival_monte_carlo(
                our_strategies=cand[:20], rival_strategy=rival_strat,
                deg_model=deg_model, pit_loss=pit_loss,
                initial_gap=gap_to_rival, n_simulations=150, noise_std=noise,
            )

        fig_h2h = plot_head_to_head_mc(
            {row["strategy"]: row["win_rate"] for _, row in h2h.head(10).iterrows()},
            rival_driver=rival_code, save=False,
        )
        st.pyplot(fig_h2h, use_container_width=True)

        st.markdown('<div class="sec-head"><span>Scan Data</span></div>', unsafe_allow_html=True)
        st.dataframe(
            scan_df.style.format({"mean_ev":"{:.3f}","p10_ev":"{:.3f}","p90_ev":"{:.3f}","win_rate":"{:.1%}"}),
            use_container_width=True, hide_index=True,
        )

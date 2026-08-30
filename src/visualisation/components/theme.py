"""
theme.py — Shared design tokens and panel primitives for Mission Control UI.
"""

from __future__ import annotations

# ── Design tokens (mirrored in CSS) ──────────────────────────────────────────
COLORS = {
    "black": "#000000",
    "off": "#080808",
    "panel": "#0f0f0f",
    "panel2": "#161616",
    "border": "#1e1e1e",
    "bord2": "#2a2a2a",
    "red": "#e8002d",
    "red2": "#ff1a3e",
    "white": "#f5f5f5",
    "dim": "#555555",
    "dim2": "#333333",
    "yellow": "#ffd700",
    "teal": "#00d2be",
    "orange": "#ff8000",
    "green": "#39b54a",
    "soft": "#E8002D",
    "medium": "#FFD700",
    "hard": "#F0F2F5",
    "inter": "#39B54A",
    "wet": "#0067FF",
}

TYRE_COLORS = {
    "SOFT": COLORS["soft"],
    "MEDIUM": COLORS["medium"],
    "HARD": COLORS["hard"],
    "INTER": COLORS["inter"],
    "WET": COLORS["wet"],
}

# ── Shared CSS injected once ─────────────────────────────────────────────────
MISSION_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Antonio:wght@100;400;700&family=Titillium+Web:ital,wght@0,200;0,300;0,400;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;600;700&display=swap');

:root {
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
  --font-m: 'JetBrains Mono', monospace;
}

*, *::before, *::after { box-sizing: border-box; }

html, body, .stApp {
  background-color: var(--black) !important;
  color: var(--white);
  font-family: var(--font-b);
}

#MainMenu, footer, header, [data-testid="stToolbar"], .stDeployButton {
  visibility: hidden !important;
  display: none !important;
}

.main .block-container {
  padding: 0.4rem 0.8rem 1.5rem !important;
  max-width: 100% !important;
  position: relative;
  z-index: 1;
}

/* ── Mission Control panels ─────────────────────────────────────────────── */
.mc-panel {
  background: var(--panel);
  border: 1px solid var(--border);
  padding: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.mc-panel-header {
  font-family: var(--font-b);
  font-size: 0.58rem;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--dim);
  padding: 0.45rem 0.7rem;
  border-bottom: 1px solid var(--border);
  background: var(--off);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.mc-panel-header .mc-title {
  color: var(--white);
  letter-spacing: 0.18em;
}
.mc-panel-body {
  padding: 0.55rem 0.7rem;
  flex: 1;
  overflow: auto;
  font-size: 0.78rem;
}
.mc-panel-body.no-pad { padding: 0; }

/* ── Top bar ────────────────────────────────────────────────────────────── */
.mc-topbar {
  display: flex;
  align-items: center;
  height: 42px;
  background: rgba(0,0,0,0.97);
  border-bottom: 1px solid var(--border);
  margin: 0 -0.8rem 0.5rem -0.8rem;
  padding: 0 0.9rem;
  gap: 1.2rem;
  position: sticky;
  top: 0;
  z-index: 100;
}
.mc-logo {
  font-family: var(--font-d);
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  color: var(--white);
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
.mc-dot {
  width: 7px; height: 7px;
  background: var(--red);
  border-radius: 50%;
  animation: mc-pulse 2s ease-in-out infinite;
}
@keyframes mc-pulse {
  0%,100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.35; transform: scale(0.75); }
}
.mc-meta {
  font-family: var(--font-b);
  font-size: 0.62rem;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--dim);
  text-transform: uppercase;
  display: flex;
  align-items: center;
  gap: 0.9rem;
}
.mc-meta strong { color: var(--white); }
.mc-badge {
  background: var(--red);
  color: white;
  font-size: 0.5rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  padding: 2px 6px;
  border-radius: 1px;
}
.mc-badge.sim { background: var(--teal); color: #000; }
.mc-badge.idle { background: var(--dim2); }

/* ── Timing tower row ───────────────────────────────────────────────────── */
.tt-row {
  display: grid;
  grid-template-columns: 28px 42px 1fr 70px 52px 48px;
  align-items: center;
  padding: 0.28rem 0.5rem;
  border-bottom: 1px solid var(--border);
  font-family: var(--font-m);
  font-size: 0.72rem;
  gap: 0.2rem;
}
.tt-row:hover { background: var(--panel2); }
.tt-row.selected { background: rgba(232,0,45,0.12); border-left: 2px solid var(--red); }
.tt-pos { color: var(--dim); font-weight: 600; }
.tt-code { font-weight: 700; letter-spacing: 0.04em; }
.tt-gap, .tt-int { color: var(--dim); text-align: right; }
.tt-age { text-align: center; color: var(--dim); }
.tt-tyre {
  width: 10px; height: 10px;
  border-radius: 50%;
  display: inline-block;
  margin-right: 4px;
  vertical-align: middle;
}

/* ── Driver status card ─────────────────────────────────────────────────── */
.drv-node {
  background: var(--panel2);
  border: 1px solid var(--bord2);
  padding: 0.55rem 0.65rem;
  margin-bottom: 0.4rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.drv-node.selected { border-color: var(--red); }
.drv-node-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.drv-node-code {
  font-family: var(--font-d);
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.drv-node-team {
  font-size: 0.55rem;
  letter-spacing: 0.1em;
  color: var(--dim);
  text-transform: uppercase;
}
.drv-node-meta {
  display: flex;
  gap: 0.7rem;
  font-family: var(--font-m);
  font-size: 0.68rem;
  color: var(--dim);
}
.drv-node-meta span strong { color: var(--white); }

/* ── Strategy / metric chips ────────────────────────────────────────────── */
.mc-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  background: var(--panel2);
  border: 1px solid var(--bord2);
  padding: 0.2rem 0.45rem;
  font-family: var(--font-m);
  font-size: 0.68rem;
  margin: 0.15rem 0.15rem 0.15rem 0;
}
.mc-chip .val { color: var(--white); font-weight: 600; }
.mc-chip .lbl { color: var(--dim); font-size: 0.58rem; letter-spacing: 0.08em; text-transform: uppercase; }

/* ── Sim progress ───────────────────────────────────────────────────────── */
.mc-progress-bar {
  height: 4px;
  background: var(--bord2);
  width: 100%;
  margin: 0.4rem 0;
}
.mc-progress-fill {
  height: 100%;
  background: var(--red);
  transition: width 0.3s ease;
}
.mc-lap-big {
  font-family: var(--font-d);
  font-size: 1.8rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  line-height: 1;
}
.mc-phase {
  font-size: 0.58rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--teal);
}

/* ── Sidebar tightening ─────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
  background: var(--off) !important;
  border-right: 1px solid var(--border) !important;
  min-width: 260px !important;
  max-width: 280px !important;
}
[data-testid="stSidebar"] > div:first-child { padding: 0 !important; }

.stSelectbox label, .stSlider label, .stRadio label, .stNumberInput label, .stCheckbox label {
  font-family: var(--font-b) !important;
  font-size: 0.58rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.18em !important;
  color: var(--dim) !important;
  text-transform: uppercase !important;
}
[data-baseweb="select"] > div {
  background: var(--panel) !important;
  border: 1px solid var(--bord2) !important;
  border-radius: 0 !important;
  color: var(--white) !important;
  font-family: var(--font-b) !important;
  font-size: 0.8rem !important;
}
.stButton > button[kind="primary"] {
  background: var(--red) !important;
  border: none !important;
  border-radius: 0 !important;
  font-family: var(--font-d) !important;
  font-size: 0.75rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.22em !important;
  color: white !important;
  width: 100% !important;
  text-transform: uppercase !important;
}
.stButton > button[kind="primary"]:hover {
  background: var(--red2) !important;
}

/* hide default streamlit padding noise */
div[data-testid="stVerticalBlock"] > div { gap: 0.35rem !important; }
</style>
"""


def inject_theme() -> None:
    """Call once at the top of the dashboard to inject Mission Control CSS."""
    import streamlit as st
    st.markdown(MISSION_CSS, unsafe_allow_html=True)


def panel(title: str, body_html: str, extra_header: str = "", no_pad: bool = False) -> str:
    """Return a self-contained Mission Control panel as HTML.

    HTML is compacted (no leading indentation) so Streamlit markdown does
    not interpret it as a fenced/indented code block and show tags as text.
    """
    pad_class = " no-pad" if no_pad else ""
    # Collapse body leading whitespace that would trigger markdown code blocks
    body = "\n".join(line.lstrip() for line in (body_html or "").splitlines())
    return (
        f'<div class="mc-panel">'
        f'<div class="mc-panel-header">'
        f'<span class="mc-title">{title}</span>'
        f'<span>{extra_header}</span>'
        f'</div>'
        f'<div class="mc-panel-body{pad_class}">{body}</div>'
        f'</div>'
    )

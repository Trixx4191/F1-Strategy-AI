"""
top_bar.py — Sticky Mission Control status bar.
"""

from __future__ import annotations

from typing import Optional


def render_top_bar(
    year: int,
    race: str,
    driver: str,
    status: str = "idle",
    track_temp: Optional[float] = None,
    weather_summary: str = "—",
) -> str:
    """
    Returns HTML for the top status bar.

    status: "idle" | "loading" | "simulating" | "ready"
    """
    badge_class = {
        "idle": "idle",
        "loading": "sim",
        "simulating": "sim",
        "ready": "",
    }.get(status, "idle")

    badge_text = {
        "idle": "IDLE",
        "loading": "LOADING",
        "simulating": "SIM RUNNING",
        "ready": "READY",
    }.get(status, "IDLE")

    temp_str = f"{track_temp:.0f}°C" if track_temp is not None else "—"

    # Same fix as theme.panel(): strip leading whitespace from every line so
    # Streamlit's markdown parser doesn't treat this as an indented code
    # block and print the raw tags instead of rendering them. This
    # component builds its own top-level wrapper rather than going through
    # panel(), so it needs the same treatment applied directly.
    html = f"""
    <div class="mc-topbar">
      <div class="mc-logo">
        <span class="mc-dot"></span>
        F1 STRATEGY AI
      </div>
      <div class="mc-meta">
        <span><strong>{year}</strong> SEASON</span>
        <span><strong>{race.upper()}</strong> GP</span>
        <span>DRIVER <strong>{driver}</strong></span>
        <span>TRACK <strong>{temp_str}</strong></span>
        <span>{weather_summary}</span>
      </div>
      <div style="margin-left:auto;display:flex;align-items:center;gap:0.6rem">
        <span class="mc-badge {badge_class}">{badge_text}</span>
      </div>
    </div>
    """
    return "\n".join(line.lstrip() for line in html.splitlines())

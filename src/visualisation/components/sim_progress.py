"""
sim_progress.py — Lap counter, stint phase, MC progress, recommended window.
"""

from __future__ import annotations

from typing import Any, Optional

from .theme import panel


def render_sim_progress(
    current_lap: int = 0,
    total_laps: int = 0,
    stint_phase: str = "—",
    mc_done: int = 0,
    mc_total: int = 0,
    recommended_window: Optional[tuple[int, int]] = None,
    title: str = "SIM PROGRESS",
) -> str:
    pct = 0.0
    if mc_total > 0:
        pct = min(100.0, 100.0 * mc_done / mc_total)

    window_str = "—"
    if recommended_window:
        window_str = f"L{recommended_window[0]}–L{recommended_window[1]}"

    body = f"""
    <div style="display:flex;flex-direction:column;gap:0.45rem">
      <div style="display:flex;justify-content:space-between;align-items:flex-end">
        <div>
          <div class="mc-lap-big">L{current_lap}<span style="font-size:0.9rem;color:var(--dim)">/{total_laps}</span></div>
          <div class="mc-phase">{stint_phase.upper()}</div>
        </div>
        <div style="text-align:right">
          <div style="font-family:var(--font-m);font-size:0.75rem;color:var(--white)">{mc_done:,} / {mc_total:,}</div>
          <div style="font-size:0.55rem;letter-spacing:0.12em;color:var(--dim)">MC ITERATIONS</div>
        </div>
      </div>
      <div class="mc-progress-bar">
        <div class="mc-progress-fill" style="width:{pct:.1f}%"></div>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:0.65rem;color:var(--dim)">
        <span>WINDOW <strong style="color:var(--white)">{window_str}</strong></span>
        <span>{pct:.0f}%</span>
      </div>
    </div>
    """
    return panel(title, body)

"""
rival_panel.py — Undercut / overcut EV summary panel.
"""

from __future__ import annotations

from typing import Any, Optional

from .theme import panel


def render_rival_panel(
    rival_code: str = "—",
    undercut_best_ev: Optional[float] = None,
    undercut_best_lap: Optional[int] = None,
    overcut_best_ev: Optional[float] = None,
    overcut_best_lap: Optional[int] = None,
    win_rate_under: Optional[float] = None,
    win_rate_over: Optional[float] = None,
    title: str = "RIVAL ENGINE",
) -> str:
    def _ev_block(label: str, ev: Optional[float], lap: Optional[int], wr: Optional[float], color: str) -> str:
        ev_str = f"{ev:+.2f}s" if ev is not None else "—"
        lap_str = f"L{lap}" if lap is not None else "—"
        wr_str = f"{wr*100:.0f}%" if wr is not None else "—"
        return f"""
        <div style="flex:1;padding:0.45rem;background:var(--panel2);border-left:2px solid {color}">
          <div style="font-size:0.55rem;letter-spacing:0.14em;color:var(--dim)">{label}</div>
          <div style="font-family:var(--font-d);font-size:1.15rem;font-weight:700;color:{color};margin:0.15rem 0">{ev_str}</div>
          <div style="font-family:var(--font-m);font-size:0.65rem;color:var(--dim)">
            BEST {lap_str} · WR {wr_str}
          </div>
        </div>
        """

    body = f"""
    <div style="font-size:0.65rem;color:var(--dim);margin-bottom:0.4rem">
      vs <strong style="color:var(--white)">{rival_code}</strong>
    </div>
    <div style="display:flex;gap:0.4rem">
      {_ev_block("UNDERCUT", undercut_best_ev, undercut_best_lap, win_rate_under, "var(--red)")}
      {_ev_block("OVERCUT", overcut_best_ev, overcut_best_lap, win_rate_over, "var(--teal)")}
    </div>
    """
    return panel(title, body)

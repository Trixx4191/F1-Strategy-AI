"""
driver_cards.py — Status nodes / cards for selected driver and key rivals.
"""

from __future__ import annotations

from typing import Any

from .theme import TYRE_COLORS, panel


def _card(d: dict[str, Any], selected: bool = False) -> str:
    code = d.get("code", "—")
    team = d.get("team", "")
    color = d.get("color", "#888")
    compound = (d.get("compound") or "—").upper()
    tyre_color = TYRE_COLORS.get(compound, "#555")
    age = d.get("tyre_age")
    age_str = str(age) if age is not None else "—"
    cliff = d.get("cliff_lap")
    cliff_str = f"{cliff:.1f}" if cliff is not None else "—"
    gap = d.get("gap_to_rival")
    gap_str = f"{gap:+.2f}s" if gap is not None else "—"
    phase = d.get("phase", "—")

    sel_class = " selected" if selected else ""
    return f"""
    <div class="drv-node{sel_class}">
      <div class="drv-node-top">
        <span class="drv-node-code" style="color:{color}">{code}</span>
        <span class="drv-node-team">{team}</span>
      </div>
      <div class="drv-node-meta">
        <span>TYRE <strong style="color:{tyre_color}">{compound}</strong> · {age_str}L</span>
        <span>CLIFF <strong>{cliff_str}</strong></span>
      </div>
      <div class="drv-node-meta">
        <span>PHASE <strong>{phase}</strong></span>
        <span>GAP <strong>{gap_str}</strong></span>
      </div>
    </div>
    """


def render_driver_cards(
    drivers: list[dict[str, Any]],
    selected_code: str | None = None,
    title: str = "DRIVER NODES",
) -> str:
    """
    drivers: list of dicts with code, team, color, compound, tyre_age,
             cliff_lap, gap_to_rival, phase
    """
    if not drivers:
        body = '<div style="color:var(--dim);font-size:0.7rem">No driver data</div>'
        return panel(title, body)

    cards = "".join(
        _card(d, selected=(d.get("code") == selected_code)) for d in drivers
    )
    return panel(title, cards, extra_header=f"{len(drivers)}")

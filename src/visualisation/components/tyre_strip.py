"""
tyre_strip.py — Bottom strip for degradation summary / cliff badges.
(Full curves still rendered via existing tyre_plots in the main dashboard.)
"""

from __future__ import annotations

from typing import Any, Optional

from .theme import TYRE_COLORS, panel


def render_tyre_strip(
    compounds: list[dict[str, Any]],
    title: str = "TYRE DEGRADATION",
) -> str:
    """
    compounds: list of {compound, cliff_lap, cliff_ci_low, cliff_ci_high, n_laps}
    """
    if not compounds:
        body = '<div style="color:var(--dim);font-size:0.7rem">Fit model to see cliff estimates</div>'
        return panel(title, body)

    chips = []
    for c in compounds:
        name = (c.get("compound") or "—").upper()
        color = TYRE_COLORS.get(name, "#888")
        cliff = c.get("cliff_lap")
        cliff_str = f"{cliff:.1f}" if cliff is not None else "—"
        lo = c.get("cliff_ci_low")
        hi = c.get("cliff_ci_high")
        ci_str = f"({lo:.1f}–{hi:.1f})" if lo is not None and hi is not None else ""
        n = c.get("n_laps", "—")
        chips.append(f"""
        <div class="mc-chip" style="border-left:3px solid {color}">
          <span class="lbl">{name}</span>
          <span class="val">CLIFF {cliff_str}</span>
          <span class="lbl">{ci_str}</span>
          <span class="lbl">n={n}</span>
        </div>
        """)

    body = f'<div style="display:flex;flex-wrap:wrap;gap:0.25rem">{"".join(chips)}</div>'
    return panel(title, body)

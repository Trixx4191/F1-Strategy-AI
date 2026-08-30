"""
timing_tower.py — Dense timing tower panel (positions, gaps, compounds).
"""

from __future__ import annotations

from typing import Any

from .theme import TYRE_COLORS, panel


def _tyre_dot(compound: str) -> str:
    color = TYRE_COLORS.get((compound or "").upper(), "#555")
    return f'<span class="tt-tyre" style="background:{color}"></span>'


def render_timing_tower(
    rows: list[dict[str, Any]],
    selected_driver: str | None = None,
    title: str = "TIMING TOWER",
) -> str:
    """
    rows: list of TimingRow-like dicts
      pos, driver, team_color, gap, interval, compound, tyre_age, last_lap
    """
    if not rows:
        body = '<div style="color:var(--dim);padding:1rem 0.5rem;font-size:0.7rem">No classification data</div>'
        return panel(title, body, no_pad=True)

    header = """
    <div class="tt-row" style="background:var(--off);font-size:0.55rem;letter-spacing:0.1em;color:var(--dim);font-family:var(--font-b)">
      <div>POS</div><div>NO</div><div>DRIVER</div><div style="text-align:right">GAP</div>
      <div style="text-align:right">INT</div><div style="text-align:center">TYRE</div>
    </div>
    """

    lines = []
    for r in rows:
        code = r.get("driver", "—")
        sel = " selected" if selected_driver and code == selected_driver else ""
        team_color = r.get("team_color") or "#555"
        gap = r.get("gap")
        interval = r.get("interval")
        pos = r.get("pos")
        if pos == 1 or gap == 0:
            gap_str = "LEADER"
        elif gap is None:
            gap_str = "—"
        else:
            gap_str = f"+{gap:.3f}"
        int_str = "—" if interval is None else f"+{interval:.3f}"
        age = r.get("tyre_age")
        age_str = str(age) if age is not None else "—"
        compound = (r.get("compound") or "").upper()
        tyre = _tyre_dot(compound) + age_str

        lines.append(f"""
        <div class="tt-row{sel}">
          <div class="tt-pos">{r.get("pos", "—")}</div>
          <div class="tt-code" style="color:{team_color}">{code}</div>
          <div style="font-family:var(--font-b);font-size:0.68rem;color:var(--dim)">{r.get("name", "")}</div>
          <div class="tt-gap">{gap_str}</div>
          <div class="tt-int">{int_str}</div>
          <div class="tt-age">{tyre}</div>
        </div>
        """)

    body = header + "".join(lines)
    return panel(title, body, extra_header=f"{len(rows)} CARS", no_pad=True)

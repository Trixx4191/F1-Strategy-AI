"""
strategy_panel.py — Top strategies + recommended pit windows.
"""

from __future__ import annotations

from typing import Any

from .theme import panel


def render_strategy_panel(
    strategies: list[dict[str, Any]],
    recommended_window: tuple[int, int] | None = None,
    title: str = "STRATEGY",
) -> str:
    """
    strategies: list of StrategyResult-like dicts
      rank, compound_sequence, pit_laps, mean_time, p10, p50, p90
    """
    if not strategies:
        body = '<div style="color:var(--dim);font-size:0.7rem">Run simulation to populate</div>'
        return panel(title, body)

    rows = []
    for s in strategies[:5]:
        compounds = " → ".join(s.get("compound_sequence") or [])
        pits = ",".join(str(p) for p in (s.get("pit_laps") or []))
        mean = s.get("mean_time")
        mean_str = f"{mean:.1f}s" if mean is not None else "—"
        p50 = s.get("p50")
        p50_str = f"{p50:.1f}" if p50 is not None else "—"
        rows.append(f"""
        <div style="display:grid;grid-template-columns:28px 1fr 70px 60px;
                    gap:0.3rem;padding:0.3rem 0;border-bottom:1px solid var(--border);
                    font-family:var(--font-m);font-size:0.7rem;align-items:center">
          <div style="color:var(--dim)">#{s.get('rank', '—')}</div>
          <div>
            <div style="color:var(--white);font-weight:600">{compounds}</div>
            <div style="color:var(--dim);font-size:0.58rem">PIT {pits or '—'}</div>
          </div>
          <div style="text-align:right;color:var(--white)">{mean_str}</div>
          <div style="text-align:right;color:var(--dim)">P50 {p50_str}</div>
        </div>
        """)

    window_html = ""
    if recommended_window:
        lo, hi = recommended_window
        window_html = f"""
        <div style="margin-top:0.5rem;padding:0.4rem 0.5rem;background:var(--panel2);
                    border-left:2px solid var(--red);font-size:0.68rem">
          <span style="color:var(--dim);letter-spacing:0.1em">RECOMMENDED WINDOW</span>
          <strong style="color:var(--white);margin-left:0.4rem">L{lo}–L{hi}</strong>
        </div>
        """

    body = "".join(rows) + window_html
    return panel(title, body, extra_header=f"TOP {min(5, len(strategies))}")

"""
track_map.py — Real circuit outline from FastF1 + driver nodes.

No hardcoded GP shapes. Geometry comes from session.get_circuit_info()
via loader.get_circuit_outline(). Falls back to a neutral placeholder
only when FastF1 has no corner data for that session.
"""

from __future__ import annotations

from typing import Any, Optional

from .theme import TYRE_COLORS, panel


def _path_from_points(points: list[dict], w: float = 100, h: float = 100) -> str:
    if not points or len(points) < 2:
        return ""
    parts = [f"M {points[0]['x']*w:.2f} {points[0]['y']*h:.2f}"]
    for p in points[1:]:
        parts.append(f"L {p['x']*w:.2f} {p['y']*h:.2f}")
    return " ".join(parts)


def _node_svg(nodes: list[dict[str, Any]], w: int = 100, h: int = 100) -> str:
    if not nodes:
        return ""
    parts = []
    n = len(nodes)
    for i, node in enumerate(nodes):
        x = node.get("x")
        y = node.get("y")
        if x is None or y is None:
            import math
            angle = 2 * math.pi * i / max(n, 1) - math.pi / 2
            x = 0.5 + 0.32 * math.cos(angle)
            y = 0.5 + 0.28 * math.sin(angle)
        compound = (node.get("compound") or "").upper()
        col = TYRE_COLORS.get(compound) or node.get("color") or "#888"
        selected = bool(node.get("selected"))
        r = 3.0 if selected else 2.1
        stroke = ' stroke="#ffffff" stroke-width="0.7"' if selected else ""
        code = node.get("code", "")
        parts.append(
            f'<circle cx="{float(x)*w:.1f}" cy="{float(y)*h:.1f}" r="{r}" '
            f'fill="{col}"{stroke}/>'
        )
        if selected and code:
            parts.append(
                f'<text x="{float(x)*w:.1f}" y="{float(y)*h - 5:.1f}" '
                f'text-anchor="middle" fill="#f5f5f5" font-size="3.5" '
                f'font-family="Antonio,sans-serif" font-weight="700">{code}</text>'
            )
    return "".join(parts)


def render_track_map(
    race_name: str = "",
    nodes: Optional[list[dict[str, Any]]] = None,
    circuit: Optional[dict[str, Any]] = None,
    title: str = "TRACK MAP",
) -> str:
    """
    circuit: output of loader.get_circuit_outline(session)
      {name, points:[{x,y}], corners:[{x,y,number}]}
    nodes: optional [{code, x, y, compound, color, selected}]
    """
    circuit = circuit or {}
    points = circuit.get("points") or []
    corners = circuit.get("corners") or []
    label = (circuit.get("name") or race_name or "CIRCUIT").upper()
    node_count = len(nodes) if nodes else 0

    path_d = _path_from_points(points)
    node_svg = _node_svg(nodes or [])

    corner_svg = ""
    for c in corners:
        corner_svg += (
            f'<circle cx="{c["x"]*100:.1f}" cy="{c["y"]*100:.1f}" r="1.2" '
            f'fill="#555"/>'
        )

    if path_d:
        svg_body = f'''
<svg viewBox="0 0 100 100" width="100%" height="200" style="max-width:340px;overflow:visible">
<path d="{path_d}" fill="none" stroke="#1a1a1a" stroke-width="6" stroke-linejoin="round" stroke-linecap="round"/>
<path d="{path_d}" fill="none" stroke="#2e2e2e" stroke-width="3.5" stroke-linejoin="round" stroke-linecap="round"/>
<path d="{path_d}" fill="none" stroke="#4a4a4a" stroke-width="1.1" stroke-linejoin="round" stroke-linecap="round"/>
{corner_svg}
{node_svg}
</svg>'''
        status = f"{len(points)} PTS"
    else:
        svg_body = '''
<div style="min-height:180px;display:flex;align-items:center;justify-content:center;
color:#555;font-size:0.65rem;letter-spacing:0.14em;text-transform:uppercase;
font-family:Titillium Web,sans-serif;text-align:center;padding:1rem">
Circuit geometry not in FastF1 for this session<br/>
<span style="opacity:0.6;font-size:0.55rem">Run simulation to load session · outline appears when available</span>
</div>'''
        status = "NO GEO"

    body = f'''
<div style="position:relative;width:100%;min-height:200px;display:flex;align-items:center;
justify-content:center;background:radial-gradient(ellipse at center,#0c0c0c 0%,#080808 70%)">
{svg_body}
<div style="position:absolute;bottom:6px;left:8px;right:8px;display:flex;
justify-content:space-between;font-family:Titillium Web,sans-serif;font-size:0.55rem;
letter-spacing:0.14em;color:#555;text-transform:uppercase">
<span>{label}</span>
<span>{node_count or "—"} NODES · {status}</span>
</div>
</div>'''
    return panel(title, body, extra_header="LIVE", no_pad=True)

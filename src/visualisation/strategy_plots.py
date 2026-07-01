"""
strategy_plots.py — Strategy comparison visualisations (redesigned).

Tighter grid lines, compound colour-coded bar segments, cleaner labels,
better pit-stop marker styling on the lap trace, improved undercut heatmap.
"""

from __future__ import annotations

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from src.utils.config import OUTPUTS_DIR
from src.utils.logger import get_logger

log = get_logger(__name__)

# ── Palette ───────────────────────────────────────────────────────────────────
BG      = "#000000"
PANEL   = "#0d0d0d"
PANEL2  = "#141414"
GRID    = "#1e1e1e"
BORDER  = "#2a2a2a"
TEXT    = "#c8c4be"
DIM     = "#555555"
RED     = "#e8002d"
YELLOW  = "#ffd700"
TEAL    = "#00d2be"
GREEN   = "#39b54a"
ORANGE  = "#ff8000"
BLUE    = "#4c9be8"

COMPOUND_COLOURS = {
    "SOFT":   RED,
    "MEDIUM": YELLOW,
    "HARD":   "#f0ede8",
    "INTER":  GREEN,
    "WET":    BLUE,
}

RANK_COLOURS = [RED, YELLOW, TEAL, ORANGE, "#aa66ff",
                "#ff6b6b", "#66ccff", "#aaffaa", "#ffaa66", "#cc88ff"]


def _theme(ax: plt.Axes, fig: plt.Figure, *, title: str = "", xlabel: str = "",
           ylabel: str = "") -> None:
    """Apply the F1-terminal dark theme to an axes."""
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)
    ax.tick_params(colors=DIM, labelsize=7.5, length=0)
    ax.xaxis.label.set_color(DIM)
    ax.yaxis.label.set_color(DIM)
    ax.title.set_color("#f5f5f5")
    for spine in ax.spines.values():
        spine.set_edgecolor(BORDER)
        spine.set_linewidth(0.5)
    ax.grid(color=GRID, linewidth=0.4, linestyle="-", alpha=1)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, fontsize=9, fontweight="bold",
                     fontfamily="monospace", color="#f5f5f5", pad=10)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=8, color=DIM)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=8, color=DIM)


def _legend(ax: plt.Axes, **kw) -> None:
    ax.legend(facecolor=PANEL2, edgecolor=BORDER, labelcolor=TEXT,
              fontsize=7.5, framealpha=1, **kw)


def _compound_segments(label: str) -> list[str]:
    """Parse 'SOFT(22) → HARD(35)' → ['SOFT', 'HARD']."""
    import re
    return re.findall(r"([A-Z]+)\(", label)


# ── Strategy comparison ───────────────────────────────────────────────────────

def plot_strategy_comparison(
    mc_results: pd.DataFrame,
    top_n: int = 15,
    save: bool = True,
    filename: str = "strategy_comparison.png",
) -> plt.Figure:
    """
    Horizontal waterfall bar chart — strategies ranked by mean race time delta.
    Each bar is colour-coded by the first compound used.
    Win rate shown as a filled bubble at the right edge.
    """
    df = mc_results.head(top_n).copy()
    best = df["mean_time"].min()
    df["delta"] = df["mean_time"] - best

    fig_h = max(6, 0.55 * top_n + 1.5)
    fig, ax = plt.subplots(figsize=(11, fig_h))
    _theme(ax, fig, title=f"STRATEGY COMPARISON — TOP {top_n}",
           xlabel="Δ Race Time vs Optimal (s)")

    y = np.arange(len(df))

    for i, (_, row) in enumerate(df.iterrows()):
        segs = _compound_segments(row["strategy"])
        colour = COMPOUND_COLOURS.get(segs[0], RANK_COLOURS[i % len(RANK_COLOURS)]) if segs else RANK_COLOURS[i % len(RANK_COLOURS)]
        alpha = 0.9 if i == 0 else 0.65

        # Main bar
        ax.barh(i, row["delta"], height=0.52, color=colour, alpha=alpha,
                left=0, zorder=3)
        # Error cap (std)
        ax.barh(i, row["std_time"], height=0.15, color=colour, alpha=0.25,
                left=row["delta"], zorder=4)

        # Compound pills at left of bar
        pill_x = -0.08
        for s in segs:
            c = COMPOUND_COLOURS.get(s, DIM)
            ax.plot(pill_x, i, "o", ms=5, color=c, zorder=5)
            pill_x -= 0.18

        # Win rate label
        wr_txt = f"{row['win_rate']:.0%}"
        ax.text(row["delta"] + row["std_time"] + 0.05, i,
                f"  {wr_txt}", va="center", fontsize=7,
                color=colour if i == 0 else DIM,
                fontfamily="monospace", zorder=5)

    # Optimal line
    ax.axvline(0, color=RED, linewidth=1.2, linestyle="--", alpha=0.6, zorder=2)
    ax.text(0.04, top_n - 0.9, "OPTIMAL", color=RED,
            fontsize=6.5, fontfamily="monospace", zorder=5, alpha=0.8)

    ax.set_yticks(y)
    labels = []
    for _, row in df.iterrows():
        suffix = " ★" if _ == 0 else ""
        labels.append(row["strategy"] + suffix)
    ax.set_yticklabels(labels, fontsize=7.5, fontfamily="monospace")
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("+%.1f"))

    # Compound legend
    handles = [mpatches.Patch(color=v, label=k, alpha=0.8)
               for k, v in COMPOUND_COLOURS.items()
               if k in ["SOFT", "MEDIUM", "HARD"]]
    ax.legend(handles=handles, loc="lower right", facecolor=PANEL2,
              edgecolor=BORDER, labelcolor=TEXT, fontsize=7.5,
              title="First compound", title_fontsize=6.5, framealpha=1)

    fig.tight_layout(pad=1.4)
    if save:
        out = OUTPUTS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"Saved: {out}")
    return fig


# ── Lap trace ─────────────────────────────────────────────────────────────────

def plot_lap_trace(
    strategies_results: list[dict],
    labels: list[str] | None = None,
    save: bool = True,
    filename: str = "lap_time_trace.png",
) -> plt.Figure:
    """
    Lap-by-lap time trace for 2–4 strategies.
    Pit stops shown as vertical dashed lines with a triangular marker.
    Stint background shading by compound.
    """
    n = len(strategies_results)
    colours = RANK_COLOURS[:n]

    fig, ax = plt.subplots(figsize=(13, 5))
    _theme(ax, fig, title="LAP-BY-LAP TIME TRACE",
           xlabel="Lap Number", ylabel="Lap Time (s)")

    y_min, y_max = float("inf"), float("-inf")

    for i, result in enumerate(strategies_results):
        label = labels[i] if labels else result.get("strategy_repr", f"Strategy {i+1}")
        colour = colours[i]
        lap_times = result["lap_times"]
        laps = np.arange(1, len(lap_times) + 1)

        y_min = min(y_min, min(lap_times))
        y_max = max(y_max, max(lap_times))

        ax.plot(laps, lap_times, color=colour, linewidth=1.8 if i == 0 else 1.2,
                label=label, alpha=0.95 if i == 0 else 0.7, zorder=4)

        # Pit stop markers — triangle + dashed line
        for pit_lap in result.get("pit_laps", []):
            ax.axvline(pit_lap, color=colour, linewidth=0.8,
                       linestyle="--", alpha=0.35, zorder=2)
            ax.scatter(pit_lap, np.interp(pit_lap, laps, lap_times),
                       marker="v", s=55, color=colour, alpha=0.9,
                       zorder=5, edgecolors="black", linewidths=0.5)
            if i == 0:  # label pit only for the first / primary strategy
                ax.text(pit_lap + 0.3, y_min,
                        f"PIT L{pit_lap}", fontsize=5.5,
                        color=colour, rotation=90, va="bottom",
                        fontfamily="monospace", alpha=0.7)

    # Zero-reference band
    ax.axhspan(y_min - 0.5, y_min + 0.3, color=PANEL2, alpha=0.4, zorder=1)

    ax.set_xlim(1, max(len(r["lap_times"]) for r in strategies_results) + 1)
    _legend(ax, loc="upper right")

    pit_marker = plt.scatter([], [], marker="v", s=55, color=DIM,
                             label="Pit stop", edgecolors="black", linewidths=0.5)
    handles, lbls = ax.get_legend_handles_labels()
    ax.legend(handles + [pit_marker], lbls + ["Pit stop"],
              facecolor=PANEL2, edgecolor=BORDER, labelcolor=TEXT,
              fontsize=7.5, framealpha=1)

    fig.tight_layout(pad=1.4)
    if save:
        out = OUTPUTS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"Saved: {out}")
    return fig


# ── Undercut window ───────────────────────────────────────────────────────────

def plot_undercut_window(
    mc_results: pd.DataFrame,
    total_laps: int,
    save: bool = True,
    filename: str = "undercut_window.png",
) -> plt.Figure | None:
    """
    Colour gradient heatmap — pit lap vs compound pair vs race time delta.
    Warmer = closer to optimal. Annotates the best pit lap per compound pair.
    """
    one_stop = mc_results[mc_results["pit_count"] == 1].copy()
    if one_stop.empty:
        return None

    def _extract_pit_lap(s):
        try:
            return int(str(s).split("(")[1].split(")")[0])
        except Exception:
            return None

    one_stop["pit_lap"] = one_stop["strategy"].apply(_extract_pit_lap)
    one_stop = one_stop.dropna(subset=["pit_lap"])
    compound_pairs = sorted(one_stop["compounds"].unique())
    n = len(compound_pairs)
    if n == 0:
        return None

    fig, axes = plt.subplots(1, n, figsize=(5.5 * n, 5), sharey=False)
    if n == 1:
        axes = [axes]
    fig.patch.set_facecolor(BG)

    best_overall = one_stop["mean_time"].min()

    # Custom colourmap: red (best) → yellow → dim grey (worst)
    cmap = LinearSegmentedColormap.from_list(
        "f1", [(0, RED), (0.35, YELLOW), (0.7, "#444"), (1.0, PANEL2)])

    for ax, pair in zip(axes, compound_pairs):
        _theme(ax, fig, title=pair, xlabel="Pit Lap",
               ylabel="Δ vs Best (s)")
        subset = one_stop[one_stop["compounds"] == pair].sort_values("pit_lap")
        if subset.empty:
            continue

        pit_laps = subset["pit_lap"].values.astype(float)
        deltas   = (subset["mean_time"].values - best_overall)
        norm_d   = (deltas - deltas.min()) / (deltas.max() - deltas.min() + 1e-9)
        colours  = [cmap(1 - v) for v in norm_d]   # invert: low delta = warm

        bars = ax.bar(pit_laps, -deltas + deltas.max(),
                      color=colours, width=0.9, zorder=3, alpha=0.9)
        ax.axhline(0, color=BORDER, linewidth=0.5)

        # Best pit lap callout
        best_idx = deltas.argmin()
        best_lap = int(pit_laps[best_idx])
        ax.annotate(
            f"OPT L{best_lap}",
            xy=(pit_laps[best_idx], -deltas[best_idx] + deltas.max()),
            xytext=(pit_laps[best_idx] + 1.5, (-deltas[best_idx] + deltas.max()) * 0.85),
            fontsize=7, color=RED, fontfamily="monospace",
            arrowprops=dict(arrowstyle="-", color=RED, lw=0.8),
        )

        # Win rate overlay line
        ax2 = ax.twinx()
        ax2.set_facecolor("none")
        ax2.plot(pit_laps, subset["win_rate"].values * 100,
                 color=TEAL, linewidth=1.2, linestyle="-", alpha=0.7, label="Win rate %")
        ax2.set_ylim(0, 100)
        ax2.tick_params(colors=TEAL, labelsize=6.5)
        ax2.set_ylabel("Win Rate (%)", fontsize=7, color=TEAL)
        for sp in ax2.spines.values():
            sp.set_edgecolor(BORDER)
            sp.set_linewidth(0.5)

    fig.suptitle("UNDERCUT WINDOW — OPTIMAL PIT LAP BY COMPOUND PAIR",
                 fontsize=10, color="#f5f5f5", fontfamily="monospace", y=1.02)
    fig.tight_layout(pad=1.4)

    if save:
        out = OUTPUTS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"Saved: {out}")
    return fig

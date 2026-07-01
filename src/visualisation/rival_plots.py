"""
rival_plots.py — Rival analysis visualisations (redesigned).

Cleaner EV timeline, gap trace with sector shading, proper H2H bar chart.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from src.utils.config import OUTPUTS_DIR
from src.utils.logger import get_logger

log = get_logger(__name__)

BG     = "#000000"
PANEL  = "#0d0d0d"
PANEL2 = "#141414"
GRID   = "#1e1e1e"
BORDER = "#2a2a2a"
TEXT   = "#c8c4be"
DIM    = "#555555"
RED    = "#e8002d"
YELLOW = "#ffd700"
TEAL   = "#00d2be"
GREEN  = "#39b54a"
ORANGE = "#ff8000"
BLUE   = "#4c9be8"


def _theme(ax, fig, *, title="", xlabel="", ylabel=""):
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)
    ax.tick_params(colors=DIM, labelsize=7.5, length=0)
    ax.xaxis.label.set_color(DIM)
    ax.yaxis.label.set_color(DIM)
    ax.title.set_color("#f5f5f5")
    for sp in ax.spines.values():
        sp.set_edgecolor(BORDER)
        sp.set_linewidth(0.5)
    ax.grid(color=GRID, linewidth=0.4, linestyle="-", alpha=1)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, fontsize=9, fontweight="bold",
                     fontfamily="monospace", color="#f5f5f5", pad=8)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=8, color=DIM)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=8, color=DIM)


# ── Undercut EV timeline ──────────────────────────────────────────────────────

def plot_undercut_ev_timeline(
    scan_df: pd.DataFrame,
    rival_driver: str,
    our_driver: str = "Our car",
    save: bool = True,
    filename: str = "undercut_ev_timeline.png",
) -> plt.Figure:
    """
    Two-panel chart:
      Top:    EV line + P10-P90 band + green/red per-lap shading
      Bottom: Win rate bars + 50% threshold line

    Full grid, compound-aware colours, clean annotations.
    """
    fig, (ax_ev, ax_wr) = plt.subplots(
        2, 1, figsize=(13, 7.5),
        gridspec_kw={"height_ratios": [2.8, 1], "hspace": 0.06},
        sharex=True,
    )
    for ax in (ax_ev, ax_wr):
        _theme(ax, fig)
    fig.patch.set_facecolor(BG)

    laps = scan_df["lap"].values
    ev   = scan_df["mean_ev"].values
    p10  = scan_df["p10_ev"].values
    p90  = scan_df["p90_ev"].values
    wr   = scan_df["win_rate"].values
    rec  = scan_df["recommend"].values

    # ── Per-lap background shading ────────────────────────────────────────────
    for i, lap in enumerate(laps):
        colour = GREEN if rec[i] else RED
        for ax in (ax_ev, ax_wr):
            ax.axvspan(lap - 0.5, lap + 0.5, alpha=0.055, color=colour, zorder=1)

    # ── Confidence band ───────────────────────────────────────────────────────
    ax_ev.fill_between(laps, p10, p90, color=BLUE, alpha=0.12,
                        label="P10–P90 range", zorder=2)
    ax_ev.fill_between(laps, 0, ev,
                        where=(ev > 0), color=GREEN, alpha=0.08, zorder=2)
    ax_ev.fill_between(laps, 0, ev,
                        where=(ev <= 0), color=RED, alpha=0.08, zorder=2)

    # ── EV line ───────────────────────────────────────────────────────────────
    ax_ev.plot(laps, ev, color=BLUE, linewidth=2, label="Mean EV", zorder=4)
    ax_ev.plot(laps, p10, color=BLUE, linewidth=0.5,
               linestyle="--", alpha=0.35, zorder=3)
    ax_ev.plot(laps, p90, color=BLUE, linewidth=0.5,
               linestyle="--", alpha=0.35, zorder=3)
    ax_ev.axhline(0, color=BORDER, linewidth=1, linestyle="-", zorder=2)

    # ── Best lap annotation ───────────────────────────────────────────────────
    if len(ev) > 0 and rec.any():
        rec_mask  = rec & (ev > 0)
        if rec_mask.any():
            best_idx = np.argmax(np.where(rec_mask, ev, -np.inf))
        else:
            best_idx = np.argmax(ev)
        ax_ev.annotate(
            f"  OPTIMAL\n  Lap {laps[best_idx]}\n  +{ev[best_idx]:.2f}s EV",
            xy=(laps[best_idx], ev[best_idx]),
            xytext=(laps[best_idx] + 1.5, ev[best_idx] + abs(ev).max() * 0.25),
            fontsize=7.5, color=GREEN, fontfamily="monospace",
            arrowprops=dict(arrowstyle="->", color=GREEN, lw=1.0),
            zorder=6,
        )

    ax_ev.set_title(
        f"UNDERCUT ANALYSIS — {our_driver} vs {rival_driver}",
        fontsize=10, fontweight="bold", fontfamily="monospace",
        color="#f5f5f5", pad=10,
    )
    ax_ev.set_ylabel("EV vs Staying Out (s)", fontsize=8, color=DIM)

    handles = [
        plt.Line2D([0], [0], color=BLUE,  linewidth=2, label="Mean EV"),
        mpatches.Patch(color=BLUE,  alpha=0.2, label="P10–P90"),
        mpatches.Patch(color=GREEN, alpha=0.3, label="Recommended"),
        mpatches.Patch(color=RED,   alpha=0.2, label="Avoid"),
    ]
    ax_ev.legend(handles=handles, facecolor=PANEL2, edgecolor=BORDER,
                  labelcolor=TEXT, fontsize=7.5, loc="upper left", framealpha=1)

    # ── Win rate bars ─────────────────────────────────────────────────────────
    bar_colours = [GREEN if r else RED for r in rec]
    ax_wr.bar(laps, wr * 100, color=bar_colours, alpha=0.8, width=0.75, zorder=3)
    ax_wr.axhline(50, color=YELLOW, linewidth=1.2, linestyle="--",
                   alpha=0.85, zorder=4, label="50% threshold")
    ax_wr.set_ylim(0, 105)
    ax_wr.set_ylabel("Win %", fontsize=7.5, color=DIM)
    ax_wr.set_xlabel("Candidate Pit Lap", fontsize=8, color=DIM)
    ax_wr.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    ax_wr.legend(facecolor=PANEL2, edgecolor=BORDER, labelcolor=TEXT,
                  fontsize=7, framealpha=1)

    for sp in ax_ev.spines.values():
        sp.set_linewidth(0.5)
    for sp in ax_wr.spines.values():
        sp.set_linewidth(0.5)

    fig.tight_layout(pad=1.4)
    if save:
        out = OUTPUTS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"Saved: {out}")
    return fig


# ── Gap trace ─────────────────────────────────────────────────────────────────

def plot_gap_trace(
    gap_per_lap: list[float],
    our_pit_laps: list[int],
    rival_pit_laps: list[int],
    our_driver: str = "Us",
    rival_driver: str = "Rival",
    save: bool = True,
    filename: str = "gap_trace.png",
) -> plt.Figure:
    """
    Lap-by-lap gap trace.
    Above zero = rival ahead. Below zero = we are ahead.
    Our pit = yellow marker. Rival pit = red marker.
    """
    fig, ax = plt.subplots(figsize=(13, 5))
    _theme(ax, fig,
           title=f"LAP-BY-LAP GAP — {our_driver} vs {rival_driver}",
           xlabel="Lap Number",
           ylabel=f"Gap: {rival_driver} − {our_driver} (s)")

    laps = np.arange(1, len(gap_per_lap) + 1)
    gap  = np.array(gap_per_lap)

    ax.fill_between(laps, gap, 0,
                    where=(gap > 0), color=RED,   alpha=0.12, label=f"{rival_driver} ahead")
    ax.fill_between(laps, gap, 0,
                    where=(gap <= 0), color=GREEN, alpha=0.12, label=f"{our_driver} ahead")
    ax.plot(laps, gap, color=BLUE, linewidth=1.8, zorder=4, label="Gap (s)")
    ax.axhline(0, color=BORDER, linewidth=1, zorder=3)

    # Smooth zero-crossing markers
    for i in range(1, len(gap)):
        if gap[i - 1] * gap[i] < 0:
            cross = laps[i - 1] + gap[i - 1] / (gap[i - 1] - gap[i])
            ax.axvline(cross, color=YELLOW, linewidth=1.2, linestyle=":",
                       alpha=0.7, zorder=3)
            label = f"{our_driver} overtakes" if gap[i] < 0 else f"{rival_driver} overtakes"
            ax.text(cross, 0, f"  {label}", fontsize=6, color=YELLOW,
                    fontfamily="monospace", va="bottom", alpha=0.8)

    # Pit stop markers
    y_range = gap.max() - gap.min() if gap.max() != gap.min() else 1
    top     = gap.max() + y_range * 0.1
    bot     = gap.min() - y_range * 0.1

    for pit_lap in our_pit_laps:
        ax.axvline(pit_lap, color=YELLOW, linewidth=1.2, linestyle="--",
                   alpha=0.6, zorder=2)
        ax.text(pit_lap, top, f"PIT\n{our_driver[:3]}",
                fontsize=6, color=YELLOW, ha="center", fontfamily="monospace",
                va="top", alpha=0.85)

    for pit_lap in rival_pit_laps:
        ax.axvline(pit_lap, color=RED, linewidth=1.2, linestyle="--",
                   alpha=0.6, zorder=2)
        ax.text(pit_lap, bot, f"PIT\n{rival_driver[:3]}",
                fontsize=6, color=RED, ha="center", fontfamily="monospace",
                va="bottom", alpha=0.85)

    # Final gap annotation
    final  = gap[-1]
    winner = rival_driver if final > 0 else our_driver
    color  = RED if final > 0 else GREEN
    ax.annotate(
        f"Finish: {winner}\nahead {abs(final):.1f}s",
        xy=(laps[-1], final),
        xytext=(laps[-1] - 8, final + (y_range * 0.25 if final < 0 else -y_range * 0.25)),
        fontsize=7.5, color=color, fontfamily="monospace",
        arrowprops=dict(arrowstyle="->", color=color, lw=0.8),
    )

    handles = [
        plt.Line2D([0], [0], color=BLUE,   linewidth=1.8, label="Gap (s)"),
        mpatches.Patch(color=RED,   alpha=0.3, label=f"{rival_driver} ahead"),
        mpatches.Patch(color=GREEN, alpha=0.3, label=f"{our_driver} ahead"),
        plt.Line2D([0], [0], color=YELLOW, linewidth=1.2, linestyle="--", label="Our pit"),
        plt.Line2D([0], [0], color=RED,    linewidth=1.2, linestyle="--", label="Rival pit"),
    ]
    ax.legend(handles=handles, facecolor=PANEL2, edgecolor=BORDER,
              labelcolor=TEXT, fontsize=7.5, framealpha=1)

    fig.tight_layout(pad=1.4)
    if save:
        out = OUTPUTS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"Saved: {out}")
    return fig


# ── Head-to-head win rate ─────────────────────────────────────────────────────

def plot_head_to_head_mc(
    our_win_rates: dict[str, float],
    rival_driver: str,
    title_suffix: str = "",
    save: bool = True,
    filename: str = "h2h_win_rates.png",
) -> plt.Figure:
    """
    Horizontal bar chart of head-to-head win rates.
    Bars: green (≥50%) / red (<50%). 50% break-even dashed line.
    Value labels at bar ends. Background gradient band.
    """
    strategies = list(our_win_rates.keys())
    win_rates  = [our_win_rates[s] * 100 for s in strategies]
    n          = len(strategies)

    fig, ax = plt.subplots(figsize=(11, max(4, 0.48 * n + 1.8)))
    _theme(ax, fig,
           title=f"HEAD-TO-HEAD WIN RATE vs {rival_driver}{title_suffix}",
           xlabel=f"Win Rate vs {rival_driver} (%)")

    y = np.arange(n)

    # Background band
    ax.axvspan(50, 100, color=GREEN, alpha=0.03, zorder=1)
    ax.axvspan(0,  50,  color=RED,   alpha=0.03, zorder=1)

    for i, (strat, wr) in enumerate(zip(strategies, win_rates)):
        colour = GREEN if wr >= 50 else RED
        ax.barh(i, wr, height=0.52, color=colour, alpha=0.8, zorder=3)
        # Label
        x_pos  = wr + 1
        anchor = "left"
        if wr > 90:
            x_pos, anchor = wr - 1, "right"
        ax.text(x_pos, i, f"{wr:.0f}%", va="center", ha=anchor,
                fontsize=7.5, color=colour if wr >= 50 else TEXT,
                fontfamily="monospace", zorder=5)

    # Break-even line
    ax.axvline(50, color=YELLOW, linewidth=1.4, linestyle="--",
               alpha=0.9, zorder=4, label="50% break-even")

    ax.set_yticks(y)
    ax.set_yticklabels(strategies, fontsize=7.5, fontfamily="monospace")
    ax.invert_yaxis()
    ax.set_xlim(0, 108)
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    ax.legend(facecolor=PANEL2, edgecolor=BORDER, labelcolor=TEXT,
              fontsize=7.5, framealpha=1)

    fig.tight_layout(pad=1.4)
    if save:
        out = OUTPUTS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"Saved: {out}")
    return fig

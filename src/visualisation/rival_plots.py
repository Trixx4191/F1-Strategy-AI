"""
rival_plots.py — Visualisations for undercut / overcut rival analysis.

Generates:
  - Undercut EV timeline (per-lap recommendation with confidence bands)
  - Gap-to-rival trace (lap-by-lap position delta across race)
  - Head-to-head strategy comparison (our sim vs rival sim)
  - Win rate bar: probability of finishing ahead for each undercut lap
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

from src.utils.config import OUTPUTS_DIR
from src.utils.logger import get_logger

log = get_logger(__name__)

DARK_BG  = "#0A0A0A"
PANEL_BG = "#141414"
GRID_COL = "#2A2A2A"
TEXT_COL = "#C8C4BE"
RED      = "#E8002D"
YELLOW   = "#FFD600"
GREEN    = "#39B54A"
BLUE     = "#0067FF"


def _apply_f1_style(ax: plt.Axes, fig: plt.Figure) -> None:
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(PANEL_BG)
    ax.tick_params(colors=TEXT_COL, labelsize=8)
    ax.xaxis.label.set_color(TEXT_COL)
    ax.yaxis.label.set_color(TEXT_COL)
    ax.title.set_color("white")
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID_COL)
    ax.grid(color=GRID_COL, linewidth=0.5, linestyle="--", alpha=0.6)
    ax.set_axisbelow(True)


def plot_undercut_ev_timeline(
    scan_df: pd.DataFrame,
    rival_driver: str,
    our_driver: str = "Our car",
    save: bool = True,
    filename: str = "undercut_ev_timeline.png",
) -> plt.Figure:
    """
    Plot undercut EV (seconds gained) per lap with P10–P90 confidence band.

    The key chart for strategy briefings:
      - X axis: candidate pit lap
      - Y axis: expected value in seconds (positive = we benefit from undercutting)
      - Green shading: laps where undercut is recommended (win_rate >= 50%)
      - Red shading: laps where undercut is -EV or too risky

    Parameters
    ----------
    scan_df       : DataFrame from rival.scan_undercut_window()
    rival_driver  : Rival driver code (for labelling)
    our_driver    : Our driver code (for labelling)
    """
    fig, (ax_ev, ax_wr) = plt.subplots(2, 1, figsize=(12, 7),
                                        gridspec_kw={"height_ratios": [3, 1]},
                                        sharex=True)

    for ax in (ax_ev, ax_wr):
        _apply_f1_style(ax, fig)

    laps = scan_df["lap"].values
    ev   = scan_df["mean_ev"].values
    p10  = scan_df["p10_ev"].values
    p90  = scan_df["p90_ev"].values
    wr   = scan_df["win_rate"].values
    rec  = scan_df["recommend"].values

    # ── EV line + confidence band ─────────────────────────────────────────────
    ax_ev.fill_between(laps, p10, p90,
                        color=BLUE, alpha=0.15, label="P10–P90 range")
    ax_ev.plot(laps, ev, color=BLUE, linewidth=2, label="Mean EV")
    ax_ev.axhline(0, color=TEXT_COL, linewidth=0.8, linestyle="--", alpha=0.5)

    # Shade recommended laps green, non-recommended red
    for i, lap in enumerate(laps):
        colour = GREEN if rec[i] else RED
        ax_ev.axvspan(lap - 0.5, lap + 0.5, alpha=0.08, color=colour)

    # Annotate the best lap
    if len(ev) > 0:
        best_idx = np.argmax(ev)
        ax_ev.annotate(
            f"Best: Lap {laps[best_idx]}\n+{ev[best_idx]:.1f}s EV",
            xy=(laps[best_idx], ev[best_idx]),
            xytext=(laps[best_idx] + 1, ev[best_idx] + 0.3),
            fontsize=8, color=GREEN, fontfamily="monospace",
            arrowprops=dict(arrowstyle="->", color=GREEN, lw=0.8),
        )

    ax_ev.set_ylabel("EV vs Staying Out (s)", fontsize=9)
    ax_ev.set_title(
        f"UNDERCUT ANALYSIS — {our_driver} vs {rival_driver}",
        fontsize=12, fontweight="bold", fontfamily="monospace",
    )
    green_patch = mpatches.Patch(color=GREEN, alpha=0.5, label="Recommended window")
    red_patch   = mpatches.Patch(color=RED,   alpha=0.3, label="Avoid")
    ax_ev.legend(handles=[
        plt.Line2D([0], [0], color=BLUE, linewidth=2, label="Mean EV"),
        mpatches.Patch(color=BLUE, alpha=0.2, label="P10–P90"),
        green_patch, red_patch,
    ], facecolor=PANEL_BG, edgecolor=GRID_COL, labelcolor=TEXT_COL, fontsize=8)

    # ── Win rate bar chart ────────────────────────────────────────────────────
    bar_colours = [GREEN if r else RED for r in rec]
    ax_wr.bar(laps, wr * 100, color=bar_colours, alpha=0.85, width=0.7)
    ax_wr.axhline(50, color=YELLOW, linewidth=1, linestyle="--", alpha=0.8,
                  label="50% threshold")
    ax_wr.set_ylim(0, 100)
    ax_wr.set_ylabel("Win Rate (%)", fontsize=8)
    ax_wr.set_xlabel("Candidate Pit Lap", fontsize=9)
    ax_wr.legend(facecolor=PANEL_BG, edgecolor=GRID_COL, labelcolor=TEXT_COL, fontsize=7)

    fig.tight_layout(pad=1.5)

    if save:
        out = OUTPUTS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"Saved: {out}")

    return fig


def plot_gap_trace(
    gap_per_lap: list[float],
    our_pit_laps: list[int],
    rival_pit_laps: list[int],
    our_driver: str = "Our car",
    rival_driver: str = "Rival",
    save: bool = True,
    filename: str = "gap_trace.png",
) -> plt.Figure:
    """
    Plot the gap to rival on every lap.

    Positive gap = rival is ahead of us.
    Negative gap = we are ahead of the rival.
    Zero crossing = position change.

    Parameters
    ----------
    gap_per_lap     : List of gap values from simulate_race_with_rival()
    our_pit_laps    : Lap numbers where we pit
    rival_pit_laps  : Lap numbers where rival pits
    """
    fig, ax = plt.subplots(figsize=(12, 5))
    _apply_f1_style(ax, fig)

    laps = list(range(1, len(gap_per_lap) + 1))
    gap  = np.array(gap_per_lap)

    # Fill above/below zero differently
    ax.fill_between(laps, gap, 0,
                    where=(gap > 0), color=RED,   alpha=0.15, label="Rival ahead")
    ax.fill_between(laps, gap, 0,
                    where=(gap < 0), color=GREEN, alpha=0.15, label="We are ahead")

    ax.plot(laps, gap, color=BLUE, linewidth=2, label="Gap (s)")
    ax.axhline(0, color=TEXT_COL, linewidth=1, linestyle="--", alpha=0.7)

    # Mark our pit stops
    for pit_lap in our_pit_laps:
        ax.axvline(pit_lap, color=YELLOW, linewidth=1.5, linestyle=":",
                   alpha=0.9, label="Our pit" if pit_lap == our_pit_laps[0] else "")
        ax.text(pit_lap, ax.get_ylim()[1] * 0.9, f"PIT\n{our_driver[:3]}",
                fontsize=6, color=YELLOW, ha="center", fontfamily="monospace")

    # Mark rival pit stops
    for pit_lap in rival_pit_laps:
        ax.axvline(pit_lap, color=RED, linewidth=1.5, linestyle=":",
                   alpha=0.9, label="Rival pit" if pit_lap == rival_pit_laps[0] else "")
        ax.text(pit_lap, ax.get_ylim()[0] * 0.9, f"PIT\n{rival_driver[:3]}",
                fontsize=6, color=RED, ha="center", fontfamily="monospace")

    # Annotate final position
    final_gap = gap[-1]
    winner = rival_driver if final_gap > 0 else our_driver
    ax.annotate(
        f"Finish: {winner} ahead by {abs(final_gap):.1f}s",
        xy=(laps[-1], final_gap),
        xytext=(laps[-1] - 10, final_gap + (2 if final_gap < 0 else -2)),
        fontsize=8, color=TEXT_COL, fontfamily="monospace",
        arrowprops=dict(arrowstyle="->", color=TEXT_COL, lw=0.7),
    )

    ax.set_xlabel("Lap Number", fontsize=9)
    ax.set_ylabel(f"Gap: {rival_driver} − {our_driver} (s)", fontsize=9)
    ax.set_title(
        f"LAP-BY-LAP GAP TRACE — {our_driver} vs {rival_driver}",
        fontsize=12, fontweight="bold", fontfamily="monospace",
    )
    handles = [
        plt.Line2D([0], [0], color=BLUE,  linewidth=2, label="Gap"),
        mpatches.Patch(color=RED,   alpha=0.3, label="Rival ahead"),
        mpatches.Patch(color=GREEN, alpha=0.3, label="We are ahead"),
        plt.Line2D([0], [0], color=YELLOW, linewidth=1.5, linestyle=":", label="Our pit"),
        plt.Line2D([0], [0], color=RED,    linewidth=1.5, linestyle=":", label="Rival pit"),
    ]
    ax.legend(handles=handles, facecolor=PANEL_BG, edgecolor=GRID_COL,
              labelcolor=TEXT_COL, fontsize=8)

    fig.tight_layout(pad=1.5)

    if save:
        out = OUTPUTS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"Saved: {out}")

    return fig


def plot_head_to_head_mc(
    our_win_rates: dict[str, float],
    rival_driver: str,
    title_suffix: str = "",
    save: bool = True,
    filename: str = "h2h_win_rates.png",
) -> plt.Figure:
    """
    Bar chart of win rate (probability of finishing ahead of rival)
    for each candidate strategy we might run.

    Parameters
    ----------
    our_win_rates : {strategy_repr: win_rate} — from run_rival_monte_carlo()
    rival_driver  : Driver code of rival (for labelling)
    """
    strategies = list(our_win_rates.keys())
    win_rates   = [our_win_rates[s] * 100 for s in strategies]

    fig, ax = plt.subplots(figsize=(10, 0.5 * len(strategies) + 2))
    _apply_f1_style(ax, fig)

    y = np.arange(len(strategies))
    colours = [GREEN if w >= 50 else RED for w in win_rates]

    ax.barh(y, win_rates, color=colours, alpha=0.85, height=0.6)
    ax.axvline(50, color=YELLOW, linewidth=1.5, linestyle="--", label="50% break-even")

    ax.set_yticks(y)
    ax.set_yticklabels(strategies, fontsize=8, fontfamily="monospace")
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel(f"Win Rate vs {rival_driver} (%)", fontsize=9)
    ax.set_title(
        f"HEAD-TO-HEAD WIN RATE vs {rival_driver}{title_suffix}",
        fontsize=11, fontweight="bold", fontfamily="monospace",
    )
    ax.legend(facecolor=PANEL_BG, edgecolor=GRID_COL, labelcolor=TEXT_COL, fontsize=8)

    # Annotate values
    for i, (w, rec) in enumerate(zip(win_rates, win_rates)):
        ax.text(w + 1, i, f"{w:.0f}%", va="center", fontsize=7,
                color=TEXT_COL, fontfamily="monospace")

    fig.tight_layout(pad=1.5)

    if save:
        out = OUTPUTS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"Saved: {out}")

    return fig

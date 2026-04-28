"""
strategy_plots.py — Strategy comparison visualisations.

Generates:
  - Monte Carlo results bar chart (top N strategies, mean ± std)
  - Win rate heatmap by pit lap
  - Lap-by-lap time trace for selected strategies
  - Undercut window chart (when is undercut vs rival +EV?)
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec

from src.utils.config import OUTPUTS_DIR
from src.utils.logger import get_logger

log = get_logger(__name__)

DARK_BG  = "#0A0A0A"
PANEL_BG = "#141414"
GRID_COL = "#2A2A2A"
TEXT_COL = "#C8C4BE"
RED      = "#E8002D"
YELLOW   = "#FFD600"

STRATEGY_COLOURS = [RED, YELLOW, "#39B54A", "#0067FF", "#FF6B00", "#AA00FF"]

COMPOUND_COLOURS = {
    "SOFT": RED, "MEDIUM": YELLOW, "HARD": "#F5F2EE",
    "INTER": "#39B54A", "WET": "#0067FF",
}


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


def plot_strategy_comparison(
    mc_results: pd.DataFrame,
    top_n: int = 10,
    save: bool = True,
    filename: str = "strategy_comparison.png",
) -> plt.Figure:
    """
    Horizontal bar chart of top N strategies with mean ± std error bars.

    Parameters
    ----------
    mc_results : DataFrame from run_monte_carlo()
    top_n      : How many strategies to show
    """
    df = mc_results.head(top_n).copy()
    # Normalise times relative to best strategy
    best = df["mean_time"].min()
    df["delta"] = df["mean_time"] - best

    fig, ax = plt.subplots(figsize=(10, 0.6 * top_n + 1.5))
    _apply_f1_style(ax, fig)

    y = np.arange(len(df))
    colours = [STRATEGY_COLOURS[i % len(STRATEGY_COLOURS)] for i in range(len(df))]

    bars = ax.barh(y, df["delta"], xerr=df["std_time"],
                   color=colours, alpha=0.85, height=0.6,
                   error_kw=dict(ecolor=TEXT_COL, capsize=3, linewidth=1))

    # Win rate annotation on bars
    for i, (_, row) in enumerate(df.iterrows()):
        ax.text(row["delta"] + row["std_time"] + 0.2,
                i, f"  {row['win_rate']:.0%} win",
                va="center", fontsize=7, color=TEXT_COL, fontfamily="monospace")

    ax.set_yticks(y)
    ax.set_yticklabels(df["strategy"], fontsize=8, fontfamily="monospace")
    ax.invert_yaxis()
    ax.set_xlabel("Δ Race Time vs Best Strategy (s)", fontsize=9)
    ax.set_title(f"TOP {top_n} STRATEGIES — MONTE CARLO", fontsize=11,
                 fontweight="bold", fontfamily="monospace")

    # Best strategy label
    ax.axvline(0, color=RED, linewidth=1.5, linestyle="--", alpha=0.7)
    ax.text(0.1, top_n - 0.5, "OPTIMAL", color=RED, fontsize=7, fontfamily="monospace")

    fig.tight_layout(pad=1.5)
    if save:
        out = OUTPUTS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"Saved: {out}")
    return fig


def plot_lap_trace(
    strategies_results: list[dict],
    labels: list[str] | None = None,
    save: bool = True,
    filename: str = "lap_time_trace.png",
) -> plt.Figure:
    """
    Plot lap-by-lap time trace for 2-3 selected strategies.

    Parameters
    ----------
    strategies_results : List of dicts from simulate_race()
    labels             : Optional override labels
    """
    fig, ax = plt.subplots(figsize=(12, 5))
    _apply_f1_style(ax, fig)

    for i, result in enumerate(strategies_results):
        label = labels[i] if labels else result.get("strategy_repr", f"Strategy {i+1}")
        colour = STRATEGY_COLOURS[i % len(STRATEGY_COLOURS)]
        lap_times = result["lap_times"]
        laps = range(1, len(lap_times) + 1)

        ax.plot(laps, lap_times, color=colour, linewidth=1.5, label=label, alpha=0.9)

        # Mark pit stops
        for pit_lap in result.get("pit_laps", []):
            ax.axvline(pit_lap, color=colour, linewidth=0.8, linestyle=":", alpha=0.5)
            ax.text(pit_lap, max(lap_times) + 0.1, "PIT", fontsize=5,
                    color=colour, rotation=90, va="bottom", ha="center",
                    fontfamily="monospace")

    ax.set_xlabel("Lap Number", fontsize=9)
    ax.set_ylabel("Lap Time (s)", fontsize=9)
    ax.set_title("LAP-BY-LAP TIME TRACE — STRATEGY COMPARISON",
                 fontsize=11, fontweight="bold", fontfamily="monospace")
    ax.legend(facecolor=PANEL_BG, edgecolor=GRID_COL, labelcolor=TEXT_COL, fontsize=8)

    fig.tight_layout(pad=1.5)
    if save:
        out = OUTPUTS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"Saved: {out}")
    return fig


def plot_undercut_window(
    mc_results: pd.DataFrame,
    total_laps: int,
    save: bool = True,
    filename: str = "undercut_window.png",
) -> plt.Figure:
    """
    Heatmap showing expected race time delta by pit lap number.
    Green cells = laps where pitting is +EV vs the mean.

    Extracts one-stop strategies and maps pit lap → mean time delta.
    """
    # Filter to one-stop only and parse pit lap from strategy string
    one_stop = mc_results[mc_results["pit_count"] == 1].copy()

    if one_stop.empty:
        log.warning("No one-stop strategies in results — cannot plot undercut window")
        return None

    # Parse pit lap from strategy string e.g. "SOFT(22) → HARD(35)"
    def _extract_pit_lap(s):
        try:
            return int(s.split("(")[1].split(")")[0])
        except Exception:
            return None

    one_stop["pit_lap"] = one_stop["strategy"].apply(_extract_pit_lap)
    one_stop = one_stop.dropna(subset=["pit_lap"])

    # Get unique compound pairs
    compound_pairs = one_stop["compounds"].unique()

    fig, axes = plt.subplots(1, len(compound_pairs),
                              figsize=(5 * len(compound_pairs), 5), sharey=False)
    if len(compound_pairs) == 1:
        axes = [axes]

    best_overall = one_stop["mean_time"].min()

    for ax, pair in zip(axes, compound_pairs):
        _apply_f1_style(ax, fig)
        subset = one_stop[one_stop["compounds"] == pair].sort_values("pit_lap")

        pit_laps = subset["pit_lap"].values
        deltas = subset["mean_time"].values - best_overall

        colours = [RED if d < 1.0 else (YELLOW if d < 3.0 else GRID_COL)
                   for d in deltas]
        ax.bar(pit_laps, -deltas, color=colours, alpha=0.85, width=0.8)
        ax.axhline(0, color=TEXT_COL, linewidth=0.8)
        ax.set_xlabel("Pit Lap", fontsize=9)
        ax.set_ylabel("Δ vs Best (s, inverted — higher = better)", fontsize=7)
        ax.set_title(pair, fontsize=9, fontfamily="monospace")

    green_patch = mpatches.Patch(color=RED, label="< 1s of optimal")
    yellow_patch = mpatches.Patch(color=YELLOW, label="1–3s of optimal")
    fig.legend(handles=[green_patch, yellow_patch],
               facecolor=PANEL_BG, edgecolor=GRID_COL, labelcolor=TEXT_COL,
               loc="lower center", ncol=2, fontsize=8, bbox_to_anchor=(0.5, -0.05))

    fig.suptitle("UNDERCUT WINDOW — OPTIMAL PIT LAPS", fontsize=11,
                 color="white", fontfamily="monospace")
    fig.tight_layout(pad=1.5)

    if save:
        out = OUTPUTS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"Saved: {out}")
    return fig

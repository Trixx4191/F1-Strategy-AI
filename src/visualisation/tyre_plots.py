"""
tyre_plots.py — Tyre degradation visualisations.

Generates:
  - Degradation curves per compound (lap time vs tyre age)
  - Stint scatter plots (actual lap data points with fitted curve overlay)
  - Compound comparison (on the same axis for quick strategy reading)
"""

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from pathlib import Path

from src.models.tyre_deg import TyreDegModel
from src.utils.config import COMPOUNDS, OUTPUTS_DIR
from src.utils.logger import get_logger

log = get_logger(__name__)

# F1-ish colour palette per compound
COMPOUND_COLOURS = {
    "SOFT":   "#E8002D",   # red
    "MEDIUM": "#FFD600",   # yellow
    "HARD":   "#F5F2EE",   # white / off-white
    "INTER":  "#39B54A",
    "WET":    "#0067FF",
}

DARK_BG  = "#0A0A0A"
PANEL_BG = "#141414"
GRID_COL = "#2A2A2A"
TEXT_COL = "#C8C4BE"


def _apply_f1_style(ax: plt.Axes, fig: plt.Figure) -> None:
    """Apply F1-broadcast-inspired dark styling to axes."""
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


def plot_degradation_curves(
    deg_model: TyreDegModel,
    max_age: int = 35,
    save: bool = True,
    filename: str = "tyre_degradation_curves.png",
) -> plt.Figure:
    """
    Plot fitted degradation curves for all compounds on one axis.

    Parameters
    ----------
    deg_model : Fitted TyreDegModel
    max_age   : Maximum tyre age to plot (laps)
    save      : Whether to save to OUTPUTS_DIR
    filename  : Output file name
    """
    fig, ax = plt.subplots(figsize=(10, 5))
    _apply_f1_style(ax, fig)

    ages = np.arange(1, max_age + 1)

    for compound in COMPOUNDS:
        if compound not in deg_model.models:
            continue
        preds = deg_model.predict(compound, ages)
        colour = COMPOUND_COLOURS.get(compound, "#888")
        ax.plot(ages, preds, label=compound, color=colour, linewidth=2.5)

        # Annotate degradation rate at lap 20
        if len(ages) >= 20:
            ax.annotate(
                f"{deg_model.deg_rate(compound, 10, 20):+.3f}s/lap",
                xy=(20, deg_model.predict(compound, 20)),
                xytext=(22, deg_model.predict(compound, 20) - 0.1),
                fontsize=7,
                color=colour,
                fontfamily="monospace",
            )

    ax.set_xlabel("Tyre Age (laps)", fontsize=9)
    ax.set_ylabel("Predicted Lap Time (s)", fontsize=9)
    ax.set_title("TYRE DEGRADATION CURVES", fontsize=12, fontweight="bold",
                 fontfamily="monospace")
    ax.legend(facecolor=PANEL_BG, edgecolor=GRID_COL, labelcolor=TEXT_COL, fontsize=8)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))

    fig.tight_layout(pad=1.5)

    if save:
        out = OUTPUTS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"Saved: {out}")

    return fig


def plot_stint_scatter(
    laps: pd.DataFrame,
    deg_model: TyreDegModel,
    driver: str | None = None,
    save: bool = True,
    filename: str = "tyre_stint_scatter.png",
) -> plt.Figure:
    """
    Scatter plot of actual lap times with fitted curve overlaid per compound.

    Parameters
    ----------
    laps      : Feature-engineered laps DataFrame
    deg_model : Fitted TyreDegModel
    driver    : Optional — filter to a single driver
    """
    fig, axes = plt.subplots(1, len(deg_model.models), figsize=(5 * len(deg_model.models), 5),
                              sharey=True)
    if len(deg_model.models) == 1:
        axes = [axes]

    title_suffix = f" — {driver}" if driver else " — All Drivers"

    for ax, compound in zip(axes, COMPOUNDS):
        if compound not in deg_model.models:
            continue

        _apply_f1_style(ax, fig)
        subset = laps[laps["Compound"] == compound]
        if driver:
            subset = subset[subset["Driver"] == driver]

        col = "FuelCorrectedLapTime" if "FuelCorrectedLapTime" in subset.columns else "LapTimeSec"
        colour = COMPOUND_COLOURS.get(compound, "#888")

        ax.scatter(subset["TyreAge"], subset[col],
                   color=colour, alpha=0.4, s=18, label="Actual")

        max_age = subset["TyreAge"].dropna()
        max_age = int(max_age.max()) if not max_age.empty else 30
        ages = np.arange(1, max_age + 1)
        preds = deg_model.predict(compound, ages)
        ax.plot(ages, preds, color=colour, linewidth=2, label="Model fit")

        ax.set_title(compound, fontsize=10, fontfamily="monospace", color=colour)
        ax.set_xlabel("Tyre Age (laps)", fontsize=8)
        ax.legend(facecolor=PANEL_BG, edgecolor=GRID_COL, labelcolor=TEXT_COL, fontsize=7)

    axes[0].set_ylabel("Lap Time (s)", fontsize=9)
    fig.suptitle(f"TYRE MODEL FIT{title_suffix}", fontsize=11,
                 color="white", fontfamily="monospace", y=1.01)
    fig.tight_layout(pad=1.5)

    if save:
        out = OUTPUTS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"Saved: {out}")

    return fig


def plot_compound_comparison_table(
    deg_model: TyreDegModel,
    save: bool = True,
    filename: str = "compound_comparison.png",
) -> plt.Figure:
    """
    Simple visual table: baseline, deg rate 1→10, deg rate 10→20 per compound.
    Fast glance for strategy discussions.
    """
    summary = deg_model.summary()
    fig, ax = plt.subplots(figsize=(8, 2.5))
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(DARK_BG)
    ax.axis("off")

    colours = [[COMPOUND_COLOURS.get(c, "#888")] + ["#F5F2EE"] * (len(summary.columns) - 1)
               for c in summary["Compound"]]

    tbl = ax.table(
        cellText=summary.values,
        colLabels=summary.columns,
        cellLoc="center",
        loc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)

    for (row, col), cell in tbl.get_celld().items():
        cell.set_edgecolor(GRID_COL)
        if row == 0:
            cell.set_facecolor(PANEL_BG)
            cell.set_text_props(color=TEXT_COL, fontfamily="monospace")
        else:
            cell.set_facecolor(PANEL_BG)
            # Colour the compound cell
            if col == 0:
                compound = summary.iloc[row - 1]["Compound"]
                cell.set_text_props(color=COMPOUND_COLOURS.get(compound, TEXT_COL),
                                    fontweight="bold")
            else:
                cell.set_text_props(color=TEXT_COL)

    fig.tight_layout()
    if save:
        out = OUTPUTS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"Saved: {out}")
    return fig

"""
tyre_plots.py — Tyre degradation visualisations (redesigned).

Three-phase piecewise model aware:
  - Colour-coded phase segments on deg curves
  - Cliff lap dashed vertical + CI shaded band
  - Stint scatter with model overlay
  - Compound comparison table
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from pathlib import Path

from src.models.tyre_deg import TyreDegModel
from src.utils.config import COMPOUNDS, OUTPUTS_DIR
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
BLUE   = "#4c9be8"

COMPOUND_COLOURS = {
    "SOFT":   RED,
    "MEDIUM": YELLOW,
    "HARD":   "#f0ede8",
    "INTER":  GREEN,
    "WET":    BLUE,
}

PHASE_ALPHA = {"bedding": 0.25, "plateau": 0.75, "cliff": 1.0}


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


def plot_degradation_curves(
    deg_model: TyreDegModel,
    max_age: int = 38,
    save: bool = True,
    filename: str = "tyre_degradation_curves.png",
) -> plt.Figure:
    """
    Piecewise-aware degradation curves.

    Segments are drawn with different line widths to show phases:
      - Bedding:  thin dashed
      - Plateau:  solid medium weight
      - Cliff:    bold solid

    Cliff lap shown as a vertical dashed line + shaded 95% CI band.
    """
    fig, ax = plt.subplots(figsize=(11, 5.5))
    _theme(ax, fig,
           title="TYRE DEGRADATION MODEL — 3-PHASE PIECEWISE FIT",
           xlabel="Tyre Age (laps)",
           ylabel="Predicted Lap Time (s)")

    ages = np.arange(1, max_age + 1)

    for compound in COMPOUNDS:
        if compound not in deg_model.models:
            continue

        cm     = deg_model.models[compound]
        colour = COMPOUND_COLOURS.get(compound, DIM)
        preds  = deg_model.predict(compound, ages)
        breaks = cm.breaks  # [start, B1, B2, end] or [start, B1, end]

        # Draw full curve first (thin, for continuity)
        ax.plot(ages, preds, color=colour, linewidth=0.5, alpha=0.25, zorder=2)

        # Draw per-phase segments with varying weight
        phase_defs = []
        if len(breaks) == 4:
            phase_defs = [
                (breaks[0], breaks[1], "bedding",  1.0,  "--"),
                (breaks[1], breaks[2], "plateau",  2.0,  "-"),
                (breaks[2], breaks[3], "cliff",    2.8,  "-"),
            ]
        elif len(breaks) == 3:
            phase_defs = [
                (breaks[0], breaks[1], "plateau",  2.0,  "-"),
                (breaks[1], breaks[2], "cliff",    2.8,  "-"),
            ]
        else:
            phase_defs = [(breaks[0], breaks[-1], "plateau", 2.0, "-")]

        for (b_start, b_end, phase, lw, ls) in phase_defs:
            seg_ages = ages[(ages >= b_start) & (ages <= b_end + 1)]
            if len(seg_ages) == 0:
                continue
            seg_preds = deg_model.predict(compound, seg_ages)
            alpha_val = PHASE_ALPHA.get(phase, 0.8)
            lbl = f"{compound} ({phase})" if phase != "plateau" else compound
            ax.plot(seg_ages, seg_preds, color=colour, linewidth=lw,
                    linestyle=ls, alpha=alpha_val, label=lbl, zorder=3)

        # Cliff marker
        cliff = deg_model.cliff_lap(compound)
        ci    = deg_model.cliff_ci(compound)
        if cliff is not None and 1 < cliff < max_age:
            ax.axvline(cliff, color=colour, linewidth=1.0,
                       linestyle=":", alpha=0.65, zorder=4)
            y_at_cliff = float(deg_model.predict(compound, int(cliff)))
            ax.scatter(cliff, y_at_cliff, s=60, color=colour,
                       marker="D", zorder=5, edgecolors="black", linewidths=0.5)
            ax.annotate(
                f"cliff ≈{cliff:.0f}L",
                xy=(cliff, y_at_cliff),
                xytext=(cliff + 0.8, y_at_cliff + 0.06),
                fontsize=6.5, color=colour, fontfamily="monospace", alpha=0.9,
            )
            if ci is not None:
                ax.axvspan(ci[0], ci[1], color=colour, alpha=0.06, zorder=1)

        # Deg rate annotation
        if max_age >= 20:
            rate = deg_model.deg_rate(compound, 10, 20)
            ax.annotate(
                f"{rate:+.3f}s/L",
                xy=(20, float(deg_model.predict(compound, 20))),
                xytext=(21.5, float(deg_model.predict(compound, 20)) - 0.05),
                fontsize=6.5, color=colour, fontfamily="monospace", alpha=0.7,
            )

    # Phase legend
    phase_handles = [
        plt.Line2D([0], [0], linewidth=1.0, linestyle="--", color=DIM, label="Bedding phase"),
        plt.Line2D([0], [0], linewidth=2.0, linestyle="-",  color=DIM, label="Plateau phase"),
        plt.Line2D([0], [0], linewidth=2.8, linestyle="-",  color=TEXT, label="Cliff phase"),
        plt.scatter([], [], marker="D", s=50, c=DIM, label="Cliff lap"),
    ]
    compound_handles = [
        mpatches.Patch(color=COMPOUND_COLOURS[c], label=c)
        for c in COMPOUNDS if c in deg_model.models
    ]
    ax.legend(
        handles=compound_handles + phase_handles,
        facecolor=PANEL2, edgecolor=BORDER, labelcolor=TEXT,
        fontsize=7.5, ncol=2, framealpha=1,
    )
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))

    fig.tight_layout(pad=1.4)
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
    Scatter of actual lap times with piecewise model overlay.
    Each compound in its own panel. Driver filter applied when supplied.
    Residuals shown as light vertical lines from points to curve.
    """
    fitted = [c for c in COMPOUNDS if c in deg_model.models]
    n = len(fitted)
    if n == 0:
        return None

    fig, axes = plt.subplots(1, n, figsize=(5.5 * n, 5.5), sharey=True)
    if n == 1:
        axes = [axes]

    driver_suffix = f" — {driver}" if driver else " — All Drivers"
    fig.suptitle(f"TYRE MODEL FIT{driver_suffix}", fontsize=10,
                 color="#f5f5f5", fontfamily="monospace", y=1.02)

    col = ("FuelCorrectedLapTime" if "FuelCorrectedLapTime" in laps.columns
           else "LapTimeSec")

    for ax, compound in zip(axes, fitted):
        _theme(ax, fig, title=compound,
               xlabel="Tyre Age (laps)",
               ylabel="Lap Time (s)" if ax == axes[0] else "")

        colour = COMPOUND_COLOURS.get(compound, DIM)
        subset = laps[laps["Compound"] == compound].copy()
        if driver:
            subset = subset[subset["Driver"] == driver]
        subset = subset.dropna(subset=["TyreAge", col])

        if subset.empty:
            ax.text(0.5, 0.5, "No data", transform=ax.transAxes,
                    ha="center", va="center", color=DIM,
                    fontfamily="monospace", fontsize=10)
            continue

        max_age = int(subset["TyreAge"].max())
        ages    = np.arange(1, max_age + 1)
        preds   = deg_model.predict(compound, ages)

        # Residual lines (scatter → curve)
        for _, row in subset.iterrows():
            age   = row["TyreAge"]
            t     = row[col]
            pred  = float(deg_model.predict(compound, age))
            ax.plot([age, age], [t, pred], color=colour,
                    alpha=0.08, linewidth=0.6, zorder=2)

        # Scatter — colour by driver if no filter
        if driver or "Driver" not in subset.columns:
            ax.scatter(subset["TyreAge"], subset[col],
                       color=colour, alpha=0.45, s=18, zorder=3,
                       edgecolors="none", label="Actual")
        else:
            for drv, grp in subset.groupby("Driver"):
                ax.scatter(grp["TyreAge"], grp[col],
                           alpha=0.3, s=14, zorder=3, edgecolors="none")

        # Model curve
        ax.plot(ages, preds, color=colour, linewidth=2.2, zorder=5,
                label="Model fit")

        # Cliff marker
        cliff = deg_model.cliff_lap(compound)
        ci    = deg_model.cliff_ci(compound)
        if cliff is not None and 1 < cliff <= max_age:
            ax.axvline(cliff, color=colour, linewidth=1.0,
                       linestyle=":", alpha=0.65, zorder=4)
            if ci:
                ax.axvspan(ci[0], ci[1], color=colour, alpha=0.06, zorder=1)
            ax.text(cliff + 0.3, subset[col].min(),
                    f"cliff ≈{cliff:.0f}L",
                    fontsize=6.5, color=colour, rotation=90, va="bottom",
                    fontfamily="monospace", alpha=0.8)

        # Fit mode badge
        mode = deg_model.fit_mode(compound)
        mode_c = {"full": GREEN, "fallback": YELLOW}.get(mode, DIM)
        ax.text(0.97, 0.04, f"{mode or '?'} · {len(subset)}L",
                transform=ax.transAxes, ha="right", va="bottom",
                fontsize=6.5, color=mode_c, fontfamily="monospace")

        ax.legend(facecolor=PANEL2, edgecolor=BORDER,
                  labelcolor=TEXT, fontsize=7.5, framealpha=1)

    fig.tight_layout(pad=1.4)
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
    Visual comparison table with colour-coded compound rows.
    Extended with cliff lap column.
    """
    summary = deg_model.summary()
    display_cols = [
        "Compound", "Baseline (s)",
        "Deg Rate 1→10 (s/lap)", "Deg Rate 10→20 (s/lap)",
        "Cliff lap", "Fit mode", "Training laps",
    ]
    display_cols = [c for c in display_cols if c in summary.columns]
    df = summary[display_cols]

    fig, ax = plt.subplots(figsize=(max(9, 1.5 * len(display_cols)), 2.5 + 0.5 * len(df)))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.axis("off")

    tbl = ax.table(
        cellText=df.values,
        colLabels=df.columns,
        cellLoc="center",
        loc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8.5)

    for (row, col), cell in tbl.get_celld().items():
        cell.set_edgecolor(BORDER)
        if row == 0:
            cell.set_facecolor(PANEL2)
            cell.set_text_props(color=DIM, fontfamily="monospace",
                                fontweight="bold")
        else:
            compound = df.iloc[row - 1]["Compound"]
            cell.set_facecolor(PANEL)
            if col == 0:
                cell.set_text_props(
                    color=COMPOUND_COLOURS.get(compound, TEXT),
                    fontweight="bold", fontfamily="monospace"
                )
            else:
                val = str(df.iloc[row - 1][df.columns[col]])
                if "cliff" in df.columns[col].lower() and val != "—":
                    cell.set_text_props(color=RED, fontfamily="monospace")
                else:
                    cell.set_text_props(color=TEXT, fontfamily="monospace")

    tbl.scale(1, 1.8)
    fig.tight_layout()
    if save:
        out = OUTPUTS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        log.info(f"Saved: {out}")
    return fig

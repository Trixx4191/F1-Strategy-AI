"""
tyre_deg.py — Tyre degradation model (piecewise linear, 3-phase).

Replaces the degree-2 polynomial with a physically accurate 3-phase model:

  Phase 1 — Bedding  (laps 1 → B₁)
      New rubber is inconsistent; lap times improve as the tyre "comes in".
      Slope is typically flat or slightly negative.

  Phase 2 — Plateau  (laps B₁ → B₂)
      Core working window. Degradation is roughly linear and predictable.
      This is the regime teams optimise strategy around.

  Phase 3 — Cliff    (laps B₂ → end)
      Abrupt phase transition as the tyre compound breaks down. Lap times
      increase sharply. The breakpoint B₂ is the cliff lap — a first-class
      output with a 95 % confidence interval.

Why piecewise linear over polynomial?
  - A parabola forces a symmetric curve; real deg has asymmetric phases.
  - The cliff is a STEP CHANGE in slope — a polynomial cannot model this.
  - The cliff lap B₂ is a directly estimated parameter with a confidence
    interval, not a derivative trick applied to a smooth curve.
  - Extrapolation beyond training data is linear (constant slope) not
    unboundedly quadratic — safer for long-stint prediction.

Implementation:
  - pwlf.PiecewiseLinFit with n_segments=3 (4 breakpoints: start, B₁, B₂, end)
  - Breakpoint positions are optimised jointly by least squares.
  - Cliff CI from the standard error of B₂ via the t-distribution.
  - public interface is identical to the old polynomial model (predict,
    deg_rate, summary) so no downstream code changes.

Usage:
    model = TyreDegModel()
    model.fit(laps_df)
    model.predict("SOFT", 18)         # → float (seconds)
    model.cliff_lap("SOFT")           # → float | None (lap number)
    model.cliff_ci("SOFT")            # → (lo, hi) | None (95 % CI)
    model.summary()                   # → DataFrame
"""

from __future__ import annotations

import warnings
import numpy as np
import pandas as pd
import pwlf
from scipy.stats import t as t_dist
from src.utils.config import COMPOUNDS
from src.utils.logger import get_logger

log = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Minimum number of clean laps required to fit a 3-segment piecewise model.
# 3 segments × ~3 data points per segment = 9 absolute minimum; 12 gives
# stable breakpoint estimates.
MIN_LAPS_FOR_FIT = 12

# Fewer than MIN_LAPS_FOR_FIT but at least this many → fall back to 2 segments
# (no bedding phase, just plateau + cliff).
MIN_LAPS_FALLBACK = 6

# The final-segment slope must exceed this (s/lap) for a cliff to be declared.
# Below this threshold the tyre is degrading but not hitting a cliff.
CLIFF_SLOPE_THRESHOLD = 0.12   # seconds per lap

# Number of bootstrap resamples for CI when SE is unavailable (sparse data).
N_BOOTSTRAP = 200

# Confidence level for cliff CI (two-tailed).
CLIFF_CI_ALPHA = 0.05


class CompoundModel:
    """
    Internal holder for one compound's fitted piecewise model and metadata.

    Attributes
    ----------
    pwlf_model   : fitted pwlf.PiecewiseLinFit
    n_segments   : int — 2 (fallback) or 3 (full)
    n_laps       : int — training data size
    breaks       : np.ndarray — fitted breakpoints
    slopes       : np.ndarray — fitted slopes per segment
    baseline     : float — predicted lap time at tyre age = 1
    mae          : float — mean absolute error on training data
    has_cliff    : bool — True if phase 3 slope qualifies as a cliff
    cliff_lap_   : float | None — estimated cliff lap (breakpoint B₂)
    cliff_ci_    : tuple[float, float] | None — 95 % CI on cliff lap
    fit_mode     : str — "full" | "fallback" | "insufficient"
    """

    def __init__(
        self,
        pwlf_model: pwlf.PiecewiseLinFit,
        n_segments: int,
        n_laps: int,
        breaks: np.ndarray,
        slopes: np.ndarray,
        baseline: float,
        mae: float,
    ):
        self.pwlf_model = pwlf_model
        self.n_segments = n_segments
        self.n_laps = n_laps
        self.breaks = breaks
        self.slopes = slopes
        self.baseline = baseline
        self.mae = mae
        self.fit_mode = "full" if n_segments == 3 else "fallback"

        self.has_cliff, self.cliff_lap_, self.cliff_ci_ = self._detect_cliff()

    # ── Cliff detection ───────────────────────────────────────────────────────

    def _detect_cliff(self) -> tuple[bool, float | None, tuple[float, float] | None]:
        """
        Determine whether the fitted model contains a genuine cliff.

        A cliff exists when:
          1. The final segment slope exceeds CLIFF_SLOPE_THRESHOLD (s/lap)
          2. The final segment is the steepest of all segments
          3. The cliff breakpoint is not at the very end of training data
             (which would indicate the model is extrapolating, not detecting)

        Returns
        -------
        (has_cliff, cliff_lap, cliff_ci)
        """
        if self.n_segments < 2:
            return False, None, None

        last_slope = self.slopes[-1]
        max_slope  = float(np.max(self.slopes))

        # Guard 1: final segment must be the steepest
        if last_slope < max_slope - 1e-6:
            return False, None, None

        # Guard 2: must exceed the cliff threshold
        if last_slope < CLIFF_SLOPE_THRESHOLD:
            return False, None, None

        # Cliff breakpoint is the second-to-last break (B₂)
        cliff_b = float(self.breaks[-2])

        # Guard 3: cliff must not be jammed against the end of the data
        data_end = float(self.breaks[-1])
        if cliff_b > data_end - 2.0:
            return False, None, None

        ci = self._cliff_confidence_interval(cliff_b)
        return True, cliff_b, ci

    def _cliff_confidence_interval(
        self, cliff_lap: float
    ) -> tuple[float, float] | None:
        """
        95 % CI on the cliff breakpoint.

        Primary method: analytical standard error from pwlf.
        Fallback: bootstrap resampling when SE is degenerate.
        """
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                se = self.pwlf_model.standard_errors()

            # se has one entry per breakpoint (incl. endpoints)
            # B₂ is index -2 (second from last)
            se_cliff = float(se[-2])

            if np.isfinite(se_cliff) and se_cliff > 0:
                n      = self.n_laps
                n_params = self.n_segments * 2
                dof    = max(n - n_params, 1)
                t_crit = float(t_dist.ppf(1 - CLIFF_CI_ALPHA / 2, dof))
                half   = t_crit * se_cliff
                return (round(cliff_lap - half, 1), round(cliff_lap + half, 1))

        except Exception:
            pass

        # Bootstrap fallback
        return self._bootstrap_ci(cliff_lap)

    def _bootstrap_ci(
        self, cliff_lap: float
    ) -> tuple[float, float] | None:
        """Bootstrap CI on cliff breakpoint via residual resampling."""
        try:
            x     = self.pwlf_model.x_data
            y_hat = self.pwlf_model.predict(x)
            resid = self.pwlf_model.y_data - y_hat
            boot_cliffs: list[float] = []

            rng = np.random.default_rng(42)
            for _ in range(N_BOOTSTRAP):
                y_boot = y_hat + rng.choice(resid, size=len(resid), replace=True)
                try:
                    m_boot = pwlf.PiecewiseLinFit(x, y_boot)
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        br = m_boot.fit(self.n_segments)
                    boot_cliffs.append(float(br[-2]))
                except Exception:
                    continue

            if len(boot_cliffs) < N_BOOTSTRAP // 2:
                return None

            lo = float(np.percentile(boot_cliffs, 2.5))
            hi = float(np.percentile(boot_cliffs, 97.5))
            return (round(lo, 1), round(hi, 1))

        except Exception:
            return None

    # ── Prediction ────────────────────────────────────────────────────────────

    def predict(self, tyre_age: np.ndarray) -> np.ndarray:
        """Predict lap times for an array of tyre ages."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return self.pwlf_model.predict(tyre_age.astype(float))


# ── TyreDegModel ──────────────────────────────────────────────────────────────

class TyreDegModel:
    """
    Per-compound piecewise-linear tyre degradation model.

    Public interface is identical to the old polynomial model so no
    downstream code (race_sim, lap_time, monte_carlo, dashboard) changes.

    New capabilities
    ----------------
    cliff_lap(compound)  → float | None   estimated cliff lap
    cliff_ci(compound)   → tuple | None   95 % CI on cliff lap
    phase_slopes(compound) → dict          slopes per phase
    summary()            → DataFrame       extended with cliff info
    """

    def __init__(self) -> None:
        self._compound_models: dict[str, CompoundModel] = {}
        self.baselines: dict[str, float] = {}
        self.is_fitted: bool = False

    # ── Fitting ───────────────────────────────────────────────────────────────

    def fit(
        self,
        laps: pd.DataFrame,
        time_col: str = "FuelCorrectedLapTime",
        driver: str | None = None,
        driver_weight: float = 4.0,
    ) -> "TyreDegModel":
        """
        Fit piecewise degradation curves per tyre compound.

        Parameters
        ----------
        laps           : Feature-engineered laps DataFrame
        time_col       : Lap time column to use as target
        driver         : Optional driver code. When supplied, that driver's
                         laps are up-weighted by driver_weight so the model
                         is personalised without losing fleet stability.
        driver_weight  : Weight multiplier for the selected driver's laps
                         (default 4 = driver laps count 4× vs fleet laps).
                         Only used when driver is not None.
        """
        if time_col not in laps.columns:
            time_col = "LapTimeSec"
            log.warning(f"FuelCorrectedLapTime not found — falling back to {time_col}")

        if driver:
            log.info(f"Fitting driver-weighted model for {driver} (weight={driver_weight}×)")

        for compound in COMPOUNDS:
            subset = laps[laps["Compound"] == compound].dropna(
                subset=["TyreAge", time_col]
            ).copy()

            n = len(subset)

            if n < MIN_LAPS_FALLBACK:
                log.warning(
                    f"{compound}: only {n} laps after cleaning — "
                    f"need at least {MIN_LAPS_FALLBACK}. Skipping."
                )
                continue

            x = subset["TyreAge"].values.astype(float)
            y = subset[time_col].values.astype(float)

            # Build sample weights: driver laps weighted up, fleet laps weight=1
            if driver and "Driver" in subset.columns:
                is_driver = (subset["Driver"] == driver).values
                n_driver  = int(is_driver.sum())
                weights   = np.where(is_driver, driver_weight, 1.0)
                log.info(
                    f"{compound}: {n} laps total | "
                    f"{n_driver} from {driver} (weight {driver_weight}×)"
                )
            else:
                weights = None

            # Choose number of segments based on data density
            n_segments = 3 if n >= MIN_LAPS_FOR_FIT else 2

            cm = self._fit_compound(compound, x, y, weights, n_segments)
            if cm is not None:
                self._compound_models[compound] = cm
                self.baselines[compound] = cm.baseline

        self.is_fitted = True
        return self

    def _fit_compound(
        self,
        compound: str,
        x: np.ndarray,
        y: np.ndarray,
        weights: np.ndarray | None,
        n_segments: int,
    ) -> CompoundModel | None:
        """
        Fit a single compound. Returns None on failure.

        pwlf optimises breakpoint positions via differential evolution
        (global optimiser) then refines with least squares. We suppress
        warnings from the optimiser — they're expected on sparse data.
        """
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                m = pwlf.PiecewiseLinFit(x, y, weights=weights)
                breaks = m.fit(n_segments)

            slopes   = m.calc_slopes()
            y_pred   = m.predict(x)
            mae      = float(np.mean(np.abs(y - y_pred)))
            baseline = float(m.predict(np.array([1.0]))[0])

            cm = CompoundModel(
                pwlf_model=m,
                n_segments=n_segments,
                n_laps=len(x),
                breaks=breaks,
                slopes=slopes,
                baseline=baseline,
                mae=mae,
            )

            cliff_str = (
                f"cliff≈lap {cm.cliff_lap_:.1f} "
                f"CI[{cm.cliff_ci_[0]:.1f},{cm.cliff_ci_[1]:.1f}]"
                if cm.has_cliff and cm.cliff_ci_
                else "no cliff detected"
            )
            log.info(
                f"{compound}: {n_segments}-seg fit | "
                f"{len(x)} laps | MAE={mae:.3f}s | "
                f"slopes={np.round(slopes,4).tolist()} | {cliff_str}"
            )
            return cm

        except Exception as e:
            log.error(f"{compound}: piecewise fit failed — {e}")
            return None

    # ── Public prediction API (unchanged from polynomial model) ───────────────

    @property
    def models(self) -> dict:
        """
        Expose compound keys so downstream code using `deg_model.models`
        continues to work (e.g. `if compound in deg_model.models`).
        """
        return self._compound_models

    def predict(self, compound: str, tyre_age: int | np.ndarray) -> float | np.ndarray:
        """
        Predict lap time for a given compound at a given tyre age.

        Parameters
        ----------
        compound  : "SOFT", "MEDIUM", or "HARD"
        tyre_age  : Integer lap age or array of ages

        Returns
        -------
        Predicted lap time(s) in seconds.
        """
        if compound not in self._compound_models:
            raise ValueError(f"No model fitted for compound: {compound}")

        scalar = np.isscalar(tyre_age)
        ages   = np.atleast_1d(np.asarray(tyre_age, dtype=float))
        result = self._compound_models[compound].predict(ages)

        return float(result[0]) if scalar else result

    def deg_rate(self, compound: str, from_lap: int = 1, to_lap: int = 20) -> float:
        """
        Average degradation rate (s/lap) between two tyre ages.

        Computed from the model predictions — preserves the piecewise
        shape so the rate correctly reflects which phase the window spans.
        """
        if compound not in self._compound_models:
            return 0.0
        t_start = self.predict(compound, from_lap)
        t_end   = self.predict(compound, to_lap)
        return (t_end - t_start) / max(to_lap - from_lap, 1)

    # ── New cliff API ─────────────────────────────────────────────────────────

    def cliff_lap(self, compound: str) -> float | None:
        """
        Return the estimated cliff lap for a compound.

        Returns None if:
          - compound not fitted
          - no cliff was detected (flat/low deg)
          - the cliff is at the very end of the data range (extrapolation risk)

        Parameters
        ----------
        compound : "SOFT", "MEDIUM", or "HARD"

        Returns
        -------
        Lap number (float) of the estimated cliff onset, or None.
        """
        cm = self._compound_models.get(compound)
        if cm is None or not cm.has_cliff:
            return None
        return cm.cliff_lap_

    def cliff_ci(self, compound: str) -> tuple[float, float] | None:
        """
        Return the 95 % confidence interval on the cliff lap.

        Returns None if no cliff was detected or CI computation failed.

        Parameters
        ----------
        compound : "SOFT", "MEDIUM", or "HARD"

        Returns
        -------
        (lower_bound, upper_bound) in lap numbers, or None.
        """
        cm = self._compound_models.get(compound)
        if cm is None or not cm.has_cliff:
            return None
        return cm.cliff_ci_

    def phase_slopes(self, compound: str) -> dict[str, float] | None:
        """
        Return the slope (s/lap) of each phase for a compound.

        Returns
        -------
        {"bedding": float, "plateau": float, "cliff": float} or
        {"plateau": float, "cliff": float} for fallback 2-segment fit,
        or None if compound not fitted.
        """
        cm = self._compound_models.get(compound)
        if cm is None:
            return None

        slopes = cm.slopes
        if len(slopes) == 3:
            return {
                "bedding": round(float(slopes[0]), 4),
                "plateau": round(float(slopes[1]), 4),
                "cliff":   round(float(slopes[2]), 4),
            }
        else:
            return {
                "plateau": round(float(slopes[0]), 4),
                "cliff":   round(float(slopes[1]), 4),
            }

    def fit_mode(self, compound: str) -> str | None:
        """
        Return the fitting mode used for a compound.

        Returns
        -------
        "full"     — 3-segment fit on ≥12 laps
        "fallback" — 2-segment fit on 6–11 laps
        None       — compound not fitted
        """
        cm = self._compound_models.get(compound)
        return cm.fit_mode if cm else None

    # ── Summary ───────────────────────────────────────────────────────────────

    def summary(self) -> pd.DataFrame:
        """
        Return a summary DataFrame of degradation metrics per compound.

        Extended vs the old model to include cliff lap, CI, and fit mode —
        these appear in the dashboard Tyre Model tab.
        """
        rows = []
        for compound in COMPOUNDS:
            cm = self._compound_models.get(compound)
            if cm is None:
                continue

            cliff_l  = cm.cliff_lap_
            cliff_lo = cm.cliff_ci_[0] if cm.cliff_ci_ else None
            cliff_hi = cm.cliff_ci_[1] if cm.cliff_ci_ else None

            rows.append({
                "Compound":               compound,
                "Baseline (s)":           round(cm.baseline, 3),
                "Deg Rate 1→10 (s/lap)":  round(self.deg_rate(compound, 1, 10), 4),
                "Deg Rate 10→20 (s/lap)": round(self.deg_rate(compound, 10, 20), 4),
                "Predicted lap 20 (s)":   round(self.predict(compound, 20), 3),
                "Cliff lap":              round(cliff_l, 1) if cliff_l else "—",
                "Cliff CI (95%)":         (
                    f"[{cliff_lo:.1f}, {cliff_hi:.1f}]"
                    if cliff_lo and cliff_hi else "—"
                ),
                "Fit mode":               cm.fit_mode,
                "Training laps":          cm.n_laps,
                "MAE (s)":                round(cm.mae, 4),
            })

        return pd.DataFrame(rows)

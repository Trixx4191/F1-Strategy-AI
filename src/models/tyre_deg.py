"""
tyre_deg.py — Tyre degradation model.

Fits a polynomial regression to lap time vs. tyre age per compound.
Used to predict how much a tyre will degrade over a given number of laps.

Why polynomial (not linear)?
  - Real degradation has a 'cliff' — slow early, then rapid
  - A degree-2 polynomial captures this inflection adequately
  - Degree 3+ overfits on typical stint lengths (15-25 laps of data)

Usage:
    model = TyreDegModel()
    model.fit(laps_df)
    predicted_time = model.predict(compound="SOFT", tyre_age=18)
"""

import numpy as np
import pandas as pd
from sklearn.preprocessing import PolynomialFeatures
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_absolute_error
from src.utils.config import COMPOUNDS, DEG_POLY_DEGREE
from src.utils.logger import get_logger

log = get_logger(__name__)


class TyreDegModel:
    """
    Per-compound polynomial degradation model.

    Attributes
    ----------
    models    : dict[compound -> sklearn Pipeline]
    baselines : dict[compound -> float] (fastest predicted lap time at age=1)
    is_fitted : bool
    """

    def __init__(self, poly_degree: int = DEG_POLY_DEGREE):
        self.poly_degree = poly_degree
        self.models: dict = {}
        self.baselines: dict = {}
        self.is_fitted = False

    def fit(self, laps: pd.DataFrame,
            time_col: str = "FuelCorrectedLapTime") -> "TyreDegModel":
        """
        Fit degradation curves per tyre compound.

        Parameters
        ----------
        laps     : Feature-engineered laps DataFrame
        time_col : Column to use as the target (prefer fuel-corrected)
        """
        if time_col not in laps.columns:
            time_col = "LapTimeSec"
            log.warning(f"FuelCorrectedLapTime not found — using {time_col}")

        for compound in COMPOUNDS:
            subset = laps[laps["Compound"] == compound].dropna(
                subset=["TyreAge", time_col]
            )

            if len(subset) < 5:
                log.warning(f"Compound {compound}: only {len(subset)} laps — skipping")
                continue

            X = subset[["TyreAge"]].values
            y = subset[time_col].values

            pipeline = Pipeline([
                ("poly", PolynomialFeatures(degree=self.poly_degree, include_bias=False)),
                ("reg", LinearRegression()),
            ])
            pipeline.fit(X, y)

            y_pred = pipeline.predict(X)
            mae = mean_absolute_error(y, y_pred)

            self.models[compound] = pipeline
            self.baselines[compound] = float(pipeline.predict([[1]])[0])

            log.info(f"{compound}: fitted on {len(subset)} laps | MAE={mae:.3f}s | "
                     f"baseline={self.baselines[compound]:.3f}s")

        self.is_fitted = True
        return self

    def predict(self, compound: str, tyre_age: int | np.ndarray) -> float | np.ndarray:
        """
        Predict lap time for a given compound at a given tyre age.

        Parameters
        ----------
        compound  : "SOFT", "MEDIUM", or "HARD"
        tyre_age  : Integer or array of tyre ages (laps on this set)

        Returns
        -------
        Predicted lap time(s) in seconds.
        """
        if compound not in self.models:
            raise ValueError(f"No model fitted for compound: {compound}")

        scalar = np.isscalar(tyre_age)
        X = np.atleast_1d(tyre_age).reshape(-1, 1)
        result = self.models[compound].predict(X)
        return float(result[0]) if scalar else result

    def deg_rate(self, compound: str, from_lap: int = 1, to_lap: int = 20) -> float:
        """
        Average degradation rate (seconds per lap) between two tyre ages.

        Useful for quick strategy comparisons:
          soft_rate = model.deg_rate("SOFT", 1, 15)
        """
        if compound not in self.models:
            return 0.0
        t_start = self.predict(compound, from_lap)
        t_end = self.predict(compound, to_lap)
        return (t_end - t_start) / (to_lap - from_lap)

    def summary(self) -> pd.DataFrame:
        """Return a summary table of degradation rates per compound."""
        rows = []
        for compound in self.models:
            rows.append({
                "Compound": compound,
                "Baseline (s)": round(self.baselines[compound], 3),
                "Deg Rate 1→10 (s/lap)": round(self.deg_rate(compound, 1, 10), 4),
                "Deg Rate 10→20 (s/lap)": round(self.deg_rate(compound, 10, 20), 4),
                "Predicted lap 20 (s)": round(self.predict(compound, 20), 3),
            })
        return pd.DataFrame(rows)

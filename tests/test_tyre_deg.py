"""
test_tyre_deg.py — Tests for the tyre degradation model.
"""

import pytest
import numpy as np
import pandas as pd
from src.models.tyre_deg import TyreDegModel


def make_tyre_data(n_per_compound: int = 25) -> pd.DataFrame:
    """
    Synthetic laps with realistic tyre degradation:
      SOFT:   faster baseline, higher deg
      MEDIUM: mid baseline, mid deg
      HARD:   slower baseline, low deg
    """
    rng = np.random.default_rng(0)
    rows = []
    specs = {
        "SOFT":   {"baseline": 89.0, "deg_per_lap": 0.12},
        "MEDIUM": {"baseline": 90.2, "deg_per_lap": 0.07},
        "HARD":   {"baseline": 91.0, "deg_per_lap": 0.04},
    }
    for compound, spec in specs.items():
        for age in range(1, n_per_compound + 1):
            lap_time = spec["baseline"] + spec["deg_per_lap"] * age + rng.normal(0, 0.08)
            rows.append({
                "Compound": compound,
                "TyreAge": age,
                "FuelCorrectedLapTime": lap_time,
                "LapTimeSec": lap_time,
                "Driver": "VER",
                "LapNumber": age,
            })
    return pd.DataFrame(rows)


class TestTyreDegModel:
    @pytest.fixture
    def fitted_model(self):
        data = make_tyre_data()
        model = TyreDegModel(poly_degree=2)
        model.fit(data)
        return model

    def test_fit_succeeds(self, fitted_model):
        assert fitted_model.is_fitted
        assert len(fitted_model.models) == 3

    def test_all_compounds_fitted(self, fitted_model):
        for compound in ["SOFT", "MEDIUM", "HARD"]:
            assert compound in fitted_model.models

    def test_predict_scalar(self, fitted_model):
        pred = fitted_model.predict("SOFT", 10)
        assert isinstance(pred, float)
        assert 85 < pred < 100  # sanity range

    def test_predict_array(self, fitted_model):
        ages = np.array([1, 5, 10, 15, 20])
        preds = fitted_model.predict("MEDIUM", ages)
        assert preds.shape == (5,)
        # Should be monotonically increasing (degrading)
        assert np.all(np.diff(preds) > 0)

    def test_soft_faster_than_hard_at_fresh_tyre(self, fitted_model):
        soft_fresh = fitted_model.predict("SOFT", 1)
        hard_fresh = fitted_model.predict("HARD", 1)
        assert soft_fresh < hard_fresh

    def test_hard_faster_than_soft_at_high_age(self, fitted_model):
        """HARD should overtake SOFT after enough laps."""
        soft_old = fitted_model.predict("SOFT", 25)
        hard_old = fitted_model.predict("HARD", 25)
        assert hard_old < soft_old

    def test_deg_rate_positive(self, fitted_model):
        for compound in ["SOFT", "MEDIUM", "HARD"]:
            rate = fitted_model.deg_rate(compound, from_lap=1, to_lap=20)
            assert rate > 0, f"{compound} deg rate should be positive"

    def test_soft_has_highest_deg_rate(self, fitted_model):
        soft_rate = fitted_model.deg_rate("SOFT", 1, 20)
        hard_rate = fitted_model.deg_rate("HARD", 1, 20)
        assert soft_rate > hard_rate

    def test_predict_unknown_compound_raises(self, fitted_model):
        with pytest.raises(ValueError, match="No model fitted"):
            fitted_model.predict("INTER", 5)

    def test_summary_returns_dataframe(self, fitted_model):
        summary = fitted_model.summary()
        assert isinstance(summary, pd.DataFrame)
        assert "Compound" in summary.columns
        assert len(summary) == 3

    def test_insufficient_data_skips_compound(self):
        """Compounds with < 5 laps should be skipped gracefully."""
        tiny = make_tyre_data(n_per_compound=3)
        model = TyreDegModel()
        model.fit(tiny)
        # All compounds skipped — is_fitted but no models
        assert model.is_fitted
        assert len(model.models) == 0

    def test_fit_uses_fallback_column(self):
        """If FuelCorrectedLapTime is missing, should fall back to LapTimeSec."""
        data = make_tyre_data()
        data = data.drop(columns=["FuelCorrectedLapTime"])
        model = TyreDegModel()
        model.fit(data)
        assert model.is_fitted

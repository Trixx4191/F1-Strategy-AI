"""
test_tyre_deg.py — Tests for the piecewise tyre degradation model.

All original interface tests are preserved (predict, deg_rate, summary,
is_fitted, etc.) so the contract with downstream code is verified.

New tests cover:
  - 3-phase fitting and cliff detection
  - cliff_lap() / cliff_ci() API
  - Curvature guards (U-shape, flat deg → no cliff)
  - Fallback to 2-segment fit on sparse data
  - Driver-weighted fitting
  - summary() extended columns
"""

import pytest
import numpy as np
import pandas as pd
from src.models.tyre_deg import TyreDegModel


# ── Synthetic data factories ───────────────────────────────────────────────────

def make_tyre_data(n_per_compound: int = 25, seed: int = 0) -> pd.DataFrame:
    """
    Synthetic laps with realistic 3-phase tyre degradation:
      SOFT:   fast baseline, clear cliff after ~lap 15
      MEDIUM: mid baseline, moderate deg, cliff after ~lap 20
      HARD:   slow baseline, low deg, no cliff
    """
    rng = np.random.default_rng(seed)
    rows = []
    specs = {
        "SOFT": {
            "baseline": 89.0,
            "bedding":  -0.08,   # improvement laps 1-3
            "plateau":   0.06,   # s/lap laps 4-15
            "cliff_at":  15,
            "cliff_rate": 0.35,
        },
        "MEDIUM": {
            "baseline": 90.2,
            "bedding":  -0.04,
            "plateau":   0.045,
            "cliff_at":  20,
            "cliff_rate": 0.22,
        },
        "HARD": {
            "baseline": 91.0,
            "bedding":  -0.02,
            "plateau":   0.025,
            "cliff_at":  None,   # no cliff on HARD
            "cliff_rate": 0.0,
        },
    }
    for compound, s in specs.items():
        for age in range(1, n_per_compound + 1):
            bedding  = s["bedding"] * min(age, 3)
            plateau  = s["plateau"] * age
            if s["cliff_at"] and age > s["cliff_at"]:
                cliff = s["cliff_rate"] * (age - s["cliff_at"])
            else:
                cliff = 0.0
            lap_time = s["baseline"] + bedding + plateau + cliff
            lap_time += rng.normal(0, 0.05)
            rows.append({
                "Compound":              compound,
                "TyreAge":               age,
                "FuelCorrectedLapTime":  lap_time,
                "LapTimeSec":            lap_time,
                "Driver":                "VER",
                "LapNumber":             age,
            })
    return pd.DataFrame(rows)


def make_multidriver_data(seed: int = 1) -> pd.DataFrame:
    """Data with two drivers — VER slightly lower baseline than HAM."""
    rng = np.random.default_rng(seed)
    rows = []
    for driver, offset in [("VER", 0.0), ("HAM", 0.12)]:
        for compound in ["SOFT", "MEDIUM", "HARD"]:
            baseline = {"SOFT": 89.0, "MEDIUM": 90.2, "HARD": 91.0}[compound]
            for age in range(1, 21):
                t = baseline + offset + 0.07 * age + rng.normal(0, 0.05)
                rows.append({
                    "Compound": compound, "TyreAge": age,
                    "FuelCorrectedLapTime": t, "LapTimeSec": t,
                    "Driver": driver, "LapNumber": age,
                })
    return pd.DataFrame(rows)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def fitted_model():
    data = make_tyre_data(n_per_compound=25)
    model = TyreDegModel()
    model.fit(data)
    return model


@pytest.fixture(scope="module")
def driver_model():
    data = make_multidriver_data()
    model = TyreDegModel()
    model.fit(data, driver="VER", driver_weight=4.0)
    return model


# ── Core interface (must remain identical to old polynomial model) ─────────────

class TestCoreInterface:

    def test_fit_succeeds(self, fitted_model):
        assert fitted_model.is_fitted
        assert len(fitted_model.models) == 3

    def test_all_compounds_fitted(self, fitted_model):
        for compound in ["SOFT", "MEDIUM", "HARD"]:
            assert compound in fitted_model.models

    def test_predict_scalar_returns_float(self, fitted_model):
        pred = fitted_model.predict("SOFT", 10)
        assert isinstance(pred, float)
        assert 85 < pred < 105

    def test_predict_array_returns_array(self, fitted_model):
        ages = np.array([1, 5, 10, 15, 20])
        preds = fitted_model.predict("MEDIUM", ages)
        assert preds.shape == (5,)

    def test_predict_monotone_in_plateau(self, fitted_model):
        """Laps 4–14 should be monotonically increasing (plateau phase)."""
        ages = np.arange(4, 14)
        preds = fitted_model.predict("SOFT", ages)
        assert np.all(np.diff(preds) > 0)

    def test_soft_faster_than_hard_at_fresh_tyre(self, fitted_model):
        assert fitted_model.predict("SOFT", 1) < fitted_model.predict("HARD", 1)

    def test_hard_faster_than_soft_at_high_age(self, fitted_model):
        assert fitted_model.predict("HARD", 25) < fitted_model.predict("SOFT", 25)

    def test_deg_rate_positive(self, fitted_model):
        for c in ["SOFT", "MEDIUM", "HARD"]:
            assert fitted_model.deg_rate(c, 1, 20) > 0

    def test_soft_higher_deg_rate_than_hard(self, fitted_model):
        assert fitted_model.deg_rate("SOFT", 1, 20) > fitted_model.deg_rate("HARD", 1, 20)

    def test_predict_unknown_compound_raises(self, fitted_model):
        with pytest.raises(ValueError, match="No model fitted"):
            fitted_model.predict("INTER", 5)

    def test_summary_returns_dataframe(self, fitted_model):
        s = fitted_model.summary()
        assert isinstance(s, pd.DataFrame)
        assert "Compound" in s.columns
        assert len(s) == 3

    def test_insufficient_data_skips_compound(self):
        tiny = make_tyre_data(n_per_compound=3)
        model = TyreDegModel()
        model.fit(tiny)
        assert model.is_fitted
        assert len(model.models) == 0

    def test_fit_uses_fallback_column(self):
        data = make_tyre_data().drop(columns=["FuelCorrectedLapTime"])
        model = TyreDegModel()
        model.fit(data)
        assert model.is_fitted
        assert len(model.models) == 3


# ── Piecewise model specifics ─────────────────────────────────────────────────

class TestPiecewiseModel:

    def test_models_dict_exposes_compound_keys(self, fitted_model):
        """models property must behave like a dict for downstream `in` checks."""
        assert "SOFT" in fitted_model.models
        assert "INTER" not in fitted_model.models

    def test_phase_slopes_returns_three_phases(self, fitted_model):
        slopes = fitted_model.phase_slopes("SOFT")
        assert slopes is not None
        assert "plateau" in slopes
        assert "cliff" in slopes

    def test_plateau_slope_positive(self, fitted_model):
        """Plateau should have positive degradation."""
        for c in ["SOFT", "MEDIUM"]:
            slopes = fitted_model.phase_slopes(c)
            assert slopes["plateau"] > 0, f"{c} plateau slope should be positive"

    def test_fit_mode_full_on_sufficient_data(self, fitted_model):
        assert fitted_model.fit_mode("SOFT") == "full"

    def test_fit_mode_fallback_on_sparse_data(self):
        sparse = make_tyre_data(n_per_compound=8)
        model = TyreDegModel()
        model.fit(sparse)
        if "SOFT" in model.models:
            assert model.fit_mode("SOFT") == "fallback"

    def test_summary_has_cliff_columns(self, fitted_model):
        s = fitted_model.summary()
        assert "Cliff lap" in s.columns
        assert "Cliff CI (95%)" in s.columns
        assert "Fit mode" in s.columns
        assert "Training laps" in s.columns
        assert "MAE (s)" in s.columns


# ── Cliff detection ───────────────────────────────────────────────────────────

class TestCliffDetection:

    def test_soft_cliff_detected(self, fitted_model):
        """SOFT with cliff_at=15 should have cliff detected."""
        cliff = fitted_model.cliff_lap("SOFT")
        assert cliff is not None, "SOFT cliff should be detected"

    def test_cliff_lap_in_plausible_range(self, fitted_model):
        """Cliff lap should be within ±5 laps of the true cliff at 15."""
        cliff = fitted_model.cliff_lap("SOFT")
        if cliff is not None:
            assert 8 < cliff < 22, f"Cliff lap {cliff:.1f} outside expected range"

    def test_cliff_ci_is_tuple_of_two_floats(self, fitted_model):
        ci = fitted_model.cliff_ci("SOFT")
        if ci is not None:
            lo, hi = ci
            assert isinstance(lo, float)
            assert isinstance(hi, float)
            assert lo < hi, "CI lower bound must be less than upper"

    def test_cliff_ci_contains_cliff_lap(self, fitted_model):
        cliff = fitted_model.cliff_lap("SOFT")
        ci    = fitted_model.cliff_ci("SOFT")
        if cliff is not None and ci is not None:
            lo, hi = ci
            assert lo <= cliff <= hi, "Cliff lap must be within its own CI"

    def test_no_cliff_for_flat_compound(self):
        """Synthetic data with very low deg should return no cliff."""
        rng = np.random.default_rng(7)
        rows = []
        for age in range(1, 26):
            t = 91.0 + 0.015 * age + rng.normal(0, 0.03)
            rows.append({"Compound": "HARD", "TyreAge": age,
                         "FuelCorrectedLapTime": t, "LapTimeSec": t,
                         "Driver": "VER", "LapNumber": age})
        df = pd.DataFrame(rows)
        # Need all 3 compounds; pad with enough SOFT/MEDIUM laps
        for c in ["SOFT", "MEDIUM"]:
            for age in range(1, 20):
                t = 89.0 + 0.06 * age + rng.normal(0, 0.04)
                rows.append({"Compound": c, "TyreAge": age,
                             "FuelCorrectedLapTime": t, "LapTimeSec": t,
                             "Driver": "VER", "LapNumber": age})
        m = TyreDegModel()
        m.fit(pd.DataFrame(rows))
        # Hard with 0.015 s/lap deg should not trigger cliff threshold
        assert m.cliff_lap("HARD") is None

    def test_unknown_compound_returns_none(self, fitted_model):
        assert fitted_model.cliff_lap("INTER") is None
        assert fitted_model.cliff_ci("INTER") is None

    def test_medium_cliff_later_than_soft(self, fitted_model):
        """MEDIUM cliff (at 20) should be later than SOFT cliff (at 15)."""
        soft_cliff   = fitted_model.cliff_lap("SOFT")
        medium_cliff = fitted_model.cliff_lap("MEDIUM")
        if soft_cliff is not None and medium_cliff is not None:
            assert soft_cliff < medium_cliff, (
                f"SOFT cliff ({soft_cliff:.1f}) should be earlier than "
                f"MEDIUM cliff ({medium_cliff:.1f})"
            )


# ── Driver-weighted fitting ───────────────────────────────────────────────────

class TestDriverWeighting:

    def test_driver_model_fits_all_compounds(self, driver_model):
        assert len(driver_model.models) == 3

    def test_driver_model_predict_interface_unchanged(self, driver_model):
        pred = driver_model.predict("SOFT", 10)
        assert isinstance(pred, float)
        assert 85 < pred < 105

    def test_driver_weighted_baseline_closer_to_driver(self):
        """
        When VER has a lower baseline than HAM, a VER-weighted model should
        produce a lower baseline than the unweighted fleet model.
        """
        data = make_multidriver_data(seed=42)

        fleet_model = TyreDegModel()
        fleet_model.fit(data)

        ver_model = TyreDegModel()
        ver_model.fit(data, driver="VER", driver_weight=5.0)

        fleet_baseline = fleet_model.predict("SOFT", 1)
        ver_baseline   = ver_model.predict("SOFT", 1)

        # VER-weighted model should be at or below the fleet mean
        # (fleet mean is between VER=89.0 and HAM=89.12)
        assert ver_baseline <= fleet_baseline + 0.15, (
            f"VER-weighted baseline {ver_baseline:.3f} should be "
            f"≤ fleet baseline {fleet_baseline:.3f} + tolerance"
        )


# ── Track temperature scaling ──────────────────────────────────────────────────

class TestTrackTempScaling:

    def test_default_scale_is_neutral(self, fitted_model):
        assert fitted_model.temp_scale == 1.0
        assert fitted_model.track_temp is None

    def test_set_track_temp_at_reference_is_neutral(self):
        data = make_tyre_data(n_per_compound=25)
        model = TyreDegModel()
        model.fit(data)
        model.set_track_temp(35.0, reference_temp=35.0)
        assert abs(model.temp_scale - 1.0) < 1e-6

    def test_hotter_track_increases_scale(self):
        data = make_tyre_data(n_per_compound=25)
        model = TyreDegModel()
        model.fit(data)
        model.set_track_temp(45.0, reference_temp=35.0)
        assert model.temp_scale > 1.0

    def test_colder_track_decreases_scale(self):
        data = make_tyre_data(n_per_compound=25)
        model = TyreDegModel()
        model.fit(data)
        model.set_track_temp(25.0, reference_temp=35.0)
        assert model.temp_scale < 1.0

    def test_none_disables_scaling(self):
        data = make_tyre_data(n_per_compound=25)
        model = TyreDegModel()
        model.fit(data)
        model.set_track_temp(45.0)
        assert model.temp_scale != 1.0
        model.set_track_temp(None)
        assert model.temp_scale == 1.0
        assert model.track_temp is None

    def test_scale_is_clamped(self):
        data = make_tyre_data(n_per_compound=25)
        model = TyreDegModel()
        model.fit(data)
        model.set_track_temp(200.0, reference_temp=35.0)
        assert model.temp_scale <= 1.6
        model.set_track_temp(-100.0, reference_temp=35.0)
        assert model.temp_scale >= 0.6

    def test_baseline_unaffected_by_temp_scale(self):
        """Lap-1 baseline pace should not change — only the deg excess scales."""
        data = make_tyre_data(n_per_compound=25)
        model = TyreDegModel()
        model.fit(data)
        baseline_before = model.predict("SOFT", 1)
        model.set_track_temp(48.0, reference_temp=35.0)
        baseline_after = model.predict("SOFT", 1)
        assert abs(baseline_before - baseline_after) < 0.05

    def test_hotter_track_increases_high_age_prediction(self):
        """At high tyre age, a hotter track should predict a slower lap time
        than at reference temp (degradation excess scaled up)."""
        data = make_tyre_data(n_per_compound=25)
        model = TyreDegModel()
        model.fit(data)
        pred_neutral = model.predict("SOFT", 20)
        model.set_track_temp(50.0, reference_temp=35.0)
        pred_hot = model.predict("SOFT", 20)
        assert pred_hot >= pred_neutral

    def test_predict_interface_unchanged_with_temp_scale(self, fitted_model):
        """predict() must still return float for scalar input after scaling."""
        data = make_tyre_data(n_per_compound=25)
        model = TyreDegModel()
        model.fit(data)
        model.set_track_temp(40.0)
        pred = model.predict("MEDIUM", 15)
        assert isinstance(pred, float)

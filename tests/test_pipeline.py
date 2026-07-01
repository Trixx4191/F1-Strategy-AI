"""
test_pipeline.py — Tests for the data loading and cleaning pipeline.

Run: pytest tests/ -v
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_sample_laps(n: int = 50) -> pd.DataFrame:
    """Create a minimal fake laps DataFrame for testing."""
    rng = np.random.default_rng(42)
    base_time = 90.0

    laps = pd.DataFrame({
        "Driver": ["VER"] * n,
        "LapNumber": np.arange(1, n + 1),
        "LapTimeSec": base_time + rng.normal(0, 0.5, n),
        "Compound": rng.choice(["SOFT", "MEDIUM", "HARD"], size=n),
        "TyreLife": np.tile(np.arange(1, 21), 3)[:n],
        "IsAccurate": [True] * (n - 3) + [False] * 3,
        "TrackStatus": ["1"] * (n - 5) + ["4"] * 5,   # 5 SC laps
        "PitInTime": [pd.NaT] * (n - 2) + [pd.Timestamp("2024-03-02 15:30:00")] * 2,
        "PitOutTime": [pd.NaT] * n,
    })
    return laps


# ── cleaner tests ─────────────────────────────────────────────────────────────

class TestCleaner:
    def test_remove_inaccurate_laps(self):
        from src.pipeline.cleaner import remove_inaccurate_laps
        laps = make_sample_laps(20)
        assert (laps["IsAccurate"] == False).sum() > 0

        cleaned = remove_inaccurate_laps(laps)
        assert (cleaned["IsAccurate"] == False).sum() == 0

    def test_remove_sc_laps(self):
        from src.pipeline.cleaner import remove_sc_laps
        laps = make_sample_laps(20)
        assert (laps["TrackStatus"] == "4").sum() > 0

        cleaned = remove_sc_laps(laps)
        assert (cleaned["TrackStatus"] != "1").sum() == 0

    def test_remove_pit_laps(self):
        from src.pipeline.cleaner import remove_pit_laps
        laps = make_sample_laps(20)
        assert laps["PitInTime"].notna().sum() > 0

        cleaned = remove_pit_laps(laps)
        assert cleaned["PitInTime"].notna().sum() == 0

    def test_outlier_removal_preserves_most_laps(self):
        from src.pipeline.cleaner import remove_lap_time_outliers
        laps = make_sample_laps(40)
        # Inject two obvious outliers
        laps.loc[5, "LapTimeSec"] = 200.0
        laps.loc[10, "LapTimeSec"] = 200.0

        cleaned = remove_lap_time_outliers(laps)
        assert len(cleaned) < len(laps)
        assert (cleaned["LapTimeSec"] > 150).sum() == 0

    def test_clean_laps_pipeline(self):
        from src.pipeline.cleaner import clean_laps
        laps = make_sample_laps(50)
        cleaned = clean_laps(laps)
        # Should have fewer laps after all filters
        assert len(cleaned) < len(laps)
        # No SC laps
        assert (cleaned["TrackStatus"] != "1").sum() == 0
        # No pit laps
        assert cleaned["PitInTime"].notna().sum() == 0


# ── features tests ─────────────────────────────────────────────────────────────

class TestFeatures:
    def get_clean_laps(self):
        from src.pipeline.cleaner import clean_laps
        laps = make_sample_laps(40)
        return clean_laps(laps)

    def test_tyre_age_added(self):
        from src.pipeline.features import add_tyre_age
        laps = self.get_clean_laps()
        result = add_tyre_age(laps)
        assert "TyreAge" in result.columns
        assert result["TyreAge"].isna().sum() == 0

    def test_fuel_corrected_lap_time(self):
        from src.pipeline.features import add_fuel_corrected_lap_time
        laps = self.get_clean_laps()
        result = add_fuel_corrected_lap_time(laps, total_laps=57)
        assert "FuelCorrectedLapTime" in result.columns
        # Early laps should be faster (more fuel = slower) so corrected < raw
        early = result[result["LapNumber"] < 10]
        assert (early["FuelCorrectedLapTime"] < early["LapTimeSec"]).all()

    def test_deg_delta_non_negative_on_average(self):
        from src.pipeline.features import engineer_features
        laps = self.get_clean_laps()
        result = engineer_features(laps, total_laps=57)
        assert "DegDelta" in result.columns
        # Mean deg delta should be non-negative (tyres get slower)
        assert result["DegDelta"].mean() >= 0


# ── loader tests (mocked — no FastF1 download needed) ─────────────────────────

class TestLoader:
    def test_get_laps_converts_timedelta(self):
        """get_laps should add *Sec columns from timedelta columns."""
        from src.pipeline.loader import get_laps

        # Build a mock session
        mock_session = MagicMock()
        mock_laps = pd.DataFrame({
            "Driver": ["VER", "NOR"],
            "LapNumber": [1, 2],
            "LapTime": pd.to_timedelta(["0:01:30.000", "0:01:31.500"]),
            "Sector1Time": pd.to_timedelta(["0:00:28.100", "0:00:28.300"]),
            "Sector2Time": pd.to_timedelta(["0:00:31.000", "0:00:31.200"]),
            "Sector3Time": pd.to_timedelta(["0:00:30.900", "0:00:32.000"]),
            "Compound": ["SOFT", "SOFT"],
            "TyreLife": [1, 2],
            "IsAccurate": [True, True],
            "TrackStatus": ["1", "1"],
            "PitInTime": [pd.NaT, pd.NaT],
            "PitOutTime": [pd.NaT, pd.NaT],
        })

        # Mock the pick_driver method
        mock_session.laps = MagicMock()
        mock_session.laps.pick_driver.return_value = mock_laps
        mock_session.laps.__getitem__ = lambda self, key: mock_laps[key]
        mock_session.laps.reset_index = lambda **kw: mock_laps.reset_index(**kw)

        # Patch pick_driver path
        result = get_laps(mock_session, driver="VER")
        assert "LapTimeSec" in result.columns
        assert result["LapTimeSec"].dtype == float

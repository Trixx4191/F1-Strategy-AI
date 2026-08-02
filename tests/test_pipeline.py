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

    def test_get_race_schedule_filters_future_events(self, monkeypatch):
        """only_completed=True must exclude events dated after today —
        this is what stops the dashboard offering a GP with no data yet."""
        from src.pipeline import loader

        today = pd.Timestamp.now().normalize()
        fake_schedule = pd.DataFrame({
            "EventName": ["Bahrain Grand Prix", "Future City Grand Prix"],
            "EventDate": [today - pd.Timedelta(days=30), today + pd.Timedelta(days=30)],
        })

        monkeypatch.setattr(loader.fastf1, "get_event_schedule", lambda *a, **kw: fake_schedule)

        result = loader.get_race_schedule(2099, only_completed=True)
        assert result == ["Bahrain"]

    def test_get_race_schedule_includes_all_when_not_filtering(self, monkeypatch):
        from src.pipeline import loader

        today = pd.Timestamp.now().normalize()
        fake_schedule = pd.DataFrame({
            "EventName": ["Bahrain Grand Prix", "Future City Grand Prix"],
            "EventDate": [today - pd.Timedelta(days=30), today + pd.Timedelta(days=30)],
        })

        monkeypatch.setattr(loader.fastf1, "get_event_schedule", lambda *a, **kw: fake_schedule)

        result = loader.get_race_schedule(2099, only_completed=False)
        assert set(result) == {"Bahrain", "Future City"}

    def test_get_race_schedule_defaults_to_completed_only(self, monkeypatch):
        """The default (no argument) must be only_completed=True — a caller
        that forgets the flag should never see an unraced future GP."""
        from src.pipeline import loader

        today = pd.Timestamp.now().normalize()
        fake_schedule = pd.DataFrame({
            "EventName": ["Past Grand Prix", "Future Grand Prix"],
            "EventDate": [today - pd.Timedelta(days=1), today + pd.Timedelta(days=1)],
        })
        monkeypatch.setattr(loader.fastf1, "get_event_schedule", lambda *a, **kw: fake_schedule)

        result = loader.get_race_schedule(2099)
        assert result == ["Past"]

    def test_get_latest_available_year_uses_current_year_if_races_exist(self, monkeypatch):
        from src.pipeline import loader
        from datetime import date

        this_year = date.today().year
        monkeypatch.setattr(loader, "get_race_schedule",
                            lambda y, only_completed=True: ["Bahrain"] if y == this_year else [])

        result = loader.get_latest_available_year()
        assert result == this_year

    def test_get_latest_available_year_falls_back_when_no_races_yet(self, monkeypatch):
        """Early January, before the first race of the new season — the
        selector should fall back to last year rather than show an empty
        season with no data."""
        from src.pipeline import loader
        from datetime import date

        this_year = date.today().year
        monkeypatch.setattr(loader, "get_race_schedule", lambda y, only_completed=True: [])

        result = loader.get_latest_available_year()
        assert result == this_year - 1

    def test_get_latest_available_year_falls_back_on_exception(self, monkeypatch):
        from src.pipeline import loader
        from datetime import date

        this_year = date.today().year
        def _raise(*a, **kw):
            raise RuntimeError("network error")
        monkeypatch.setattr(loader, "get_race_schedule", _raise)

        result = loader.get_latest_available_year()
        assert result == this_year - 1


# ── Column preservation regression tests ────────────────────────────────────
#
# groupby().apply(..., include_groups=False) silently drops the grouping
# column(s) from the result. This previously caused "Compound" to vanish
# from clean_laps() output, and BOTH "Driver" and "StintNumber" to vanish
# from engineer_features() output — breaking every downstream consumer that
# filters or groups by those columns (tyre_deg.py's driver-weighted fit,
# the dashboard's driver selector, etc). These tests guard against that
# class of regression by explicitly checking the full pipeline's output
# schema with MULTI-DRIVER data (a single-driver fixture wouldn't catch
# the Driver-column-loss case, since a 1-driver groupby "losing" Driver
# is invisible if nothing downstream ever filters by it in the test).

def make_multidriver_laps(n_per_driver: int = 30) -> pd.DataFrame:
    """Multi-driver, multi-stint fake laps — needed to catch column-loss
    regressions in groupby operations keyed on Driver/StintNumber/Compound."""
    rng = np.random.default_rng(7)
    rows = []
    for driver, base in [("VER", 90.0), ("HAM", 90.3), ("LEC", 90.15)]:
        tyre_age = 0
        stint_switch_at = n_per_driver // 2
        for lap_num in range(1, n_per_driver + 1):
            tyre_age = tyre_age + 1 if lap_num != stint_switch_at else 1
            compound = "SOFT" if lap_num < stint_switch_at else "HARD"
            rows.append({
                "Driver": driver,
                "LapNumber": lap_num,
                "LapTimeSec": base + 0.05 * tyre_age + rng.normal(0, 0.3),
                "Compound": compound,
                "TyreLife": tyre_age,
                "IsAccurate": True,
                "TrackStatus": "1",
                "PitInTime": pd.NaT,
                "PitOutTime": pd.NaT,
            })
    return pd.DataFrame(rows)


class TestPipelineColumnPreservation:
    """Guards against groupby().apply() silently dropping grouping columns."""

    def test_clean_laps_preserves_compound_column(self):
        from src.pipeline.cleaner import clean_laps
        laps = make_multidriver_laps()
        cleaned = clean_laps(laps)
        assert "Compound" in cleaned.columns, (
            "Compound column was dropped during cleaning — "
            "check remove_lap_time_outliers for groupby() column loss"
        )

    def test_clean_laps_compound_values_intact(self):
        from src.pipeline.cleaner import clean_laps
        laps = make_multidriver_laps()
        cleaned = clean_laps(laps)
        assert set(cleaned["Compound"].unique()) <= {"SOFT", "MEDIUM", "HARD"}
        assert len(cleaned) > 0

    def test_engineer_features_preserves_driver_column(self):
        from src.pipeline.cleaner import clean_laps
        from src.pipeline.features import engineer_features
        laps = make_multidriver_laps()
        cleaned = clean_laps(laps)
        result = engineer_features(cleaned, total_laps=30)
        assert "Driver" in result.columns, (
            "Driver column was dropped during feature engineering — "
            "check add_deg_delta for groupby() column loss"
        )

    def test_engineer_features_preserves_stint_number_column(self):
        from src.pipeline.cleaner import clean_laps
        from src.pipeline.features import engineer_features
        laps = make_multidriver_laps()
        cleaned = clean_laps(laps)
        result = engineer_features(cleaned, total_laps=30)
        assert "StintNumber" in result.columns

    def test_engineer_features_driver_values_intact_multidriver(self):
        """The regression only shows up with >1 driver — a 1-driver
        fixture can't distinguish 'column present' from 'column dropped
        then silently re-inferred'."""
        from src.pipeline.cleaner import clean_laps
        from src.pipeline.features import engineer_features
        laps = make_multidriver_laps()
        cleaned = clean_laps(laps)
        result = engineer_features(cleaned, total_laps=30)
        assert set(result["Driver"].unique()) == {"VER", "HAM", "LEC"}

    def test_full_pipeline_schema_has_all_required_columns(self):
        """End-to-end: every column the tyre model and dashboard depend on
        must survive clean_laps() -> engineer_features()."""
        from src.pipeline.cleaner import clean_laps
        from src.pipeline.features import engineer_features
        laps = make_multidriver_laps()
        cleaned = clean_laps(laps)
        result = engineer_features(cleaned, total_laps=30)

        required = {
            "Driver", "Compound", "TyreAge", "StintNumber",
            "FuelCorrectedLapTime", "DegDelta", "LapTimeSec", "LapNumber",
        }
        missing = required - set(result.columns)
        assert not missing, f"Pipeline dropped required columns: {missing}"

    def test_deg_delta_first_lap_of_stint_is_zero(self):
        """Sanity check the transform-based DegDelta matches the original
        apply-based semantics: first lap of each stint has DegDelta == 0."""
        from src.pipeline.cleaner import clean_laps
        from src.pipeline.features import engineer_features
        laps = make_multidriver_laps()
        cleaned = clean_laps(laps)
        result = engineer_features(cleaned, total_laps=30)

        first_laps = result.sort_values("LapNumber").groupby(
            ["Driver", "StintNumber"]
        ).first()
        assert np.allclose(first_laps["DegDelta"], 0.0, atol=1e-9)

    def test_outlier_removal_keeps_small_groups_fully(self):
        """Groups with <3 laps should be kept entirely (can't judge outliers
        on so little data) — verifies the vectorized transform matches the
        original per-group apply() logic exactly."""
        from src.pipeline.cleaner import remove_lap_time_outliers
        laps = pd.DataFrame({
            "Compound": ["SOFT", "SOFT"] + ["HARD"] * 11,
            "LapTimeSec": [90.0, 90.2] + [91.0, 91.1, 91.2, 90.9, 91.05,
                                          91.15, 90.95, 91.1, 91.0, 91.05,
                                          110.0],  # HARD has one clear outlier
        })
        result = remove_lap_time_outliers(laps, z_threshold=2.5)
        # SOFT group (n=2 < 3) must survive fully
        assert (result["Compound"] == "SOFT").sum() == 2
        # HARD group's 110.0 outlier should be removed (mean~91.4, well
        # away from the tight cluster of normal laps around 91.0)
        assert 110.0 not in result["LapTimeSec"].values

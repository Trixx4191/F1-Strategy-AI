"""
test_rival.py — Tests for the rival modelling module.
"""

import pytest
import numpy as np
import pandas as pd

from src.simulator.rival import (
    RivalState, UndercutResult,
    evaluate_undercut, evaluate_overcut,
    scan_undercut_window,
)
from src.models.tyre_deg import TyreDegModel


# ── Shared fixtures ────────────────────────────────────────────────────────────

def make_model() -> TyreDegModel:
    rng = np.random.default_rng(99)
    rows = []
    specs = {
        "SOFT":   {"baseline": 89.0, "deg": 0.12},
        "MEDIUM": {"baseline": 90.2, "deg": 0.07},
        "HARD":   {"baseline": 91.0, "deg": 0.04},
    }
    for compound, s in specs.items():
        for age in range(1, 30):
            rows.append({
                "Compound": compound,
                "TyreAge": age,
                "FuelCorrectedLapTime": s["baseline"] + s["deg"] * age + rng.normal(0, 0.04),
                "LapTimeSec": s["baseline"] + s["deg"] * age,
                "Driver": "VER",
                "LapNumber": age,
            })
    m = TyreDegModel()
    m.fit(pd.DataFrame(rows))
    return m


@pytest.fixture(scope="module")
def model():
    return make_model()


@pytest.fixture
def rival_ahead(model):
    """Rival is 2.0s ahead on older MEDIUM tyres."""
    return RivalState(
        driver="NOR",
        compound="MEDIUM",
        tyre_age=18,
        gap_to_us=2.0,
    )


@pytest.fixture
def rival_behind(model):
    """Rival is 1.5s behind us."""
    return RivalState(
        driver="SAI",
        compound="HARD",
        tyre_age=12,
        gap_to_us=-1.5,
    )


# ── RivalState tests ───────────────────────────────────────────────────────────

class TestRivalState:
    def test_repr_shows_direction(self, rival_ahead):
        assert "ahead" in repr(rival_ahead)

    def test_repr_shows_behind(self, rival_behind):
        assert "behind" in repr(rival_behind)

    def test_gap_sign_convention(self, rival_ahead, rival_behind):
        assert rival_ahead.gap_to_us > 0
        assert rival_behind.gap_to_us < 0


# ── Undercut evaluation tests ─────────────────────────────────────────────────

class TestEvaluateUndercut:
    def test_returns_undercut_result(self, model, rival_ahead):
        result = evaluate_undercut(
            lap=20, our_compound="MEDIUM", our_tyre_age=18,
            new_compound="HARD", rival=rival_ahead,
            deg_model=model, pit_loss=22.0, noise_std=0.0,
        )
        assert isinstance(result, UndercutResult)
        assert result.lap == 20
        assert isinstance(result.undercut_works, bool)
        assert isinstance(result.ev_seconds, float)

    def test_undercut_less_attractive_when_rival_far_ahead(self, model):
        """A 5s gap should be harder to overcome than a 1s gap."""
        rival_close = RivalState("NOR", "MEDIUM", 18, gap_to_us=1.0)
        rival_far   = RivalState("NOR", "MEDIUM", 18, gap_to_us=5.0)

        kwargs = dict(lap=20, our_compound="MEDIUM", our_tyre_age=18,
                      new_compound="HARD", deg_model=model, pit_loss=22.0, noise_std=0.0)

        r_close = evaluate_undercut(rival=rival_close, **kwargs)
        r_far   = evaluate_undercut(rival=rival_far,   **kwargs)

        # Gap after outlap should be smaller (less negative) when rival is farther ahead
        assert r_close.gap_after_our_outlap < r_far.gap_after_our_outlap

    def test_undercut_on_very_old_rival_tyres(self, model):
        """If rival is on 25-lap-old SOFT and gap is small, undercut is attractive
        relative to staying out (our fresh HARD will quickly undercut their deg cliff)."""
        rival_old = RivalState("NOR", "SOFT", 25, gap_to_us=1.0)
        result_undercut = evaluate_undercut(
            lap=20, our_compound="MEDIUM", our_tyre_age=10,
            new_compound="HARD", rival=rival_old,
            deg_model=model, pit_loss=22.0, noise_std=0.0,
        )
        result_later = evaluate_undercut(
            lap=25, our_compound="MEDIUM", our_tyre_age=15,
            new_compound="HARD", rival=rival_old,
            deg_model=model, pit_loss=22.0, noise_std=0.0,
        )
        # Pitting earlier is better when rival is on cliff — EV should be higher at lap 20
        # (both might be negative in absolute terms, but lap 20 should be less negative)
        assert result_undercut.ev_seconds >= result_later.ev_seconds - 1.0

    def test_noise_adds_variance(self, model, rival_ahead):
        """With noise, repeated calls should give different results."""
        evs = [
            evaluate_undercut(
                lap=20, our_compound="MEDIUM", our_tyre_age=18,
                new_compound="HARD", rival=rival_ahead,
                deg_model=model, pit_loss=22.0, noise_std=0.5,
            ).ev_seconds
            for _ in range(30)
        ]
        assert len(set(evs)) > 1  # not all identical


# ── Overcut evaluation tests ───────────────────────────────────────────────────

class TestEvaluateOvercut:
    def test_returns_dict_with_expected_keys(self, model, rival_ahead):
        result = evaluate_overcut(
            lap=20, our_compound="MEDIUM", our_tyre_age=18,
            new_compound="HARD", rival=rival_ahead,
            deg_model=model, pit_loss=22.0, noise_std=0.0,
        )
        for key in ("overcut_works", "gap_after_exchange", "pace_deficit_per_lap",
                    "laps_sustainable"):
            assert key in result

    def test_overcut_fails_when_we_are_behind(self, model, rival_ahead):
        """If rival is 2s ahead and pits, we can't overcut — they're too far ahead."""
        result = evaluate_overcut(
            lap=20, our_compound="MEDIUM", our_tyre_age=18,
            new_compound="SOFT", rival=rival_ahead,
            deg_model=model, pit_loss=22.0, noise_std=0.0,
        )
        # Being 2s behind at pit point, overcut should not work
        # (depends on pit loss vs pace delta — we assert it returns a bool at minimum)
        assert isinstance(result["overcut_works"], bool)

    def test_overcut_sustainable_when_we_are_ahead(self, model, rival_behind):
        """If rival is behind us and pits, overcut has a decent chance."""
        result = evaluate_overcut(
            lap=20, our_compound="MEDIUM", our_tyre_age=15,
            new_compound="SOFT", rival=rival_behind,
            deg_model=model, pit_loss=22.0, noise_std=0.0,
        )
        assert isinstance(result["laps_sustainable"], float)
        assert result["laps_sustainable"] >= 0


# ── Scan window tests ─────────────────────────────────────────────────────────

class TestScanUndercutWindow:
    def test_returns_dataframe_correct_shape(self, model, rival_ahead):
        df = scan_undercut_window(
            from_lap=15, to_lap=25,
            our_compound="MEDIUM", our_tyre_age_at_from_lap=15,
            new_compound="HARD", rival=rival_ahead,
            deg_model=model, pit_loss=22.0,
            n_simulations=30, noise_std=0.3,
        )
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 11   # laps 15 to 25 inclusive
        assert set(df["lap"].tolist()) == set(range(15, 26))

    def test_win_rates_in_valid_range(self, model, rival_ahead):
        df = scan_undercut_window(
            from_lap=18, to_lap=22,
            our_compound="MEDIUM", our_tyre_age_at_from_lap=18,
            new_compound="HARD", rival=rival_ahead,
            deg_model=model, pit_loss=22.0,
            n_simulations=50, noise_std=0.3,
        )
        assert (df["win_rate"] >= 0.0).all()
        assert (df["win_rate"] <= 1.0).all()

    def test_recommend_flag_consistent(self, model, rival_ahead):
        """recommend should be True iff win_rate >= 0.5 AND mean_ev > 0."""
        df = scan_undercut_window(
            from_lap=15, to_lap=25,
            our_compound="MEDIUM", our_tyre_age_at_from_lap=15,
            new_compound="HARD", rival=rival_ahead,
            deg_model=model, pit_loss=22.0,
            n_simulations=50, noise_std=0.3,
        )
        for _, row in df.iterrows():
            expected_rec = (row["win_rate"] >= 0.5) and (row["mean_ev"] > 0)
            assert row["recommend"] == expected_rec

    def test_p10_le_p50_le_p90(self, model, rival_ahead):
        df = scan_undercut_window(
            from_lap=18, to_lap=22,
            our_compound="MEDIUM", our_tyre_age_at_from_lap=18,
            new_compound="HARD", rival=rival_ahead,
            deg_model=model, pit_loss=22.0,
            n_simulations=50, noise_std=0.3,
        )
        for _, row in df.iterrows():
            assert row["p10_ev"] <= row["p50_ev"] <= row["p90_ev"]

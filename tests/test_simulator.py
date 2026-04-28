"""
test_simulator.py — Tests for the race simulation and Monte Carlo engine.
"""

import pytest
import numpy as np
import pandas as pd

from src.simulator.strategy import Stint, Strategy, generate_one_stop_strategies, generate_two_stop_strategies
from src.simulator.race_sim import simulate_race, compare_strategies
from src.simulator.monte_carlo import run_monte_carlo
from src.models.tyre_deg import TyreDegModel


# ── Shared fixtures ───────────────────────────────────────────────────────────

def make_fitted_model() -> TyreDegModel:
    rng = np.random.default_rng(7)
    rows = []
    specs = {
        "SOFT":   {"baseline": 89.0, "deg": 0.12},
        "MEDIUM": {"baseline": 90.2, "deg": 0.07},
        "HARD":   {"baseline": 91.0, "deg": 0.04},
    }
    for compound, s in specs.items():
        for age in range(1, 30):
            rows.append({
                "Compound": compound, "TyreAge": age,
                "FuelCorrectedLapTime": s["baseline"] + s["deg"] * age + rng.normal(0, 0.05),
                "LapTimeSec": s["baseline"] + s["deg"] * age,
                "Driver": "VER", "LapNumber": age,
            })
    model = TyreDegModel()
    model.fit(pd.DataFrame(rows))
    return model


@pytest.fixture(scope="module")
def model():
    return make_fitted_model()


# ── Strategy tests ────────────────────────────────────────────────────────────

class TestStrategy:
    def test_strategy_total_laps(self):
        strat = Strategy([Stint("SOFT", 22), Stint("HARD", 35)])
        assert strat.total_laps == 57

    def test_strategy_pit_count(self):
        strat = Strategy([Stint("SOFT", 22), Stint("HARD", 35)])
        assert strat.pit_count == 1

    def test_strategy_is_valid_different_compounds(self):
        strat = Strategy([Stint("SOFT", 22), Stint("HARD", 35)])
        assert strat.is_valid

    def test_strategy_invalid_same_compound(self):
        strat = Strategy([Stint("MEDIUM", 30), Stint("MEDIUM", 27)])
        assert not strat.is_valid

    def test_generate_one_stop_count(self):
        strategies = generate_one_stop_strategies(total_laps=57, min_stint=8)
        assert len(strategies) > 0
        # All should be valid
        assert all(s.is_valid for s in strategies)
        # All should sum to 57 laps
        assert all(s.total_laps == 57 for s in strategies)

    def test_generate_two_stop_count(self):
        strategies = generate_two_stop_strategies(total_laps=57, min_stint=10)
        assert len(strategies) > 0
        assert all(s.total_laps == 57 for s in strategies)
        assert all(s.pit_count == 2 for s in strategies)


# ── Race sim tests ────────────────────────────────────────────────────────────

class TestRaceSim:
    def test_simulate_race_returns_dict(self, model):
        strat = Strategy([Stint("SOFT", 22), Stint("HARD", 35)])
        result = simulate_race(strat, model, pit_loss=22.0, noise_std=0.0)
        assert isinstance(result, dict)
        assert "total_time" in result
        assert "lap_times" in result
        assert "pit_laps" in result

    def test_lap_count_matches_strategy(self, model):
        strat = Strategy([Stint("SOFT", 22), Stint("HARD", 35)])
        result = simulate_race(strat, model, pit_loss=22.0)
        assert len(result["lap_times"]) == 57

    def test_pit_laps_correct(self, model):
        strat = Strategy([Stint("SOFT", 22), Stint("HARD", 35)])
        result = simulate_race(strat, model, pit_loss=22.0)
        assert result["pit_laps"] == [22]

    def test_noise_adds_variance(self, model):
        strat = Strategy([Stint("MEDIUM", 28), Stint("HARD", 29)])
        t1 = simulate_race(strat, model, pit_loss=22.0, noise_std=0.0)["total_time"]
        times = [simulate_race(strat, model, pit_loss=22.0, noise_std=0.5)["total_time"]
                 for _ in range(50)]
        assert np.std(times) > 0.1  # noise adds spread
        # Mean should be close to deterministic (within 5s)
        assert abs(np.mean(times) - t1) < 5.0

    def test_compare_strategies_sorted(self, model):
        strategies = generate_one_stop_strategies(57, min_stint=15)[:20]
        results = compare_strategies(strategies, model, pit_loss=22.0)
        times = [r["total_time"] for r in results]
        assert times == sorted(times)


# ── Monte Carlo tests ─────────────────────────────────────────────────────────

class TestMonteCarlo:
    def test_mc_returns_dataframe(self, model):
        strategies = generate_one_stop_strategies(57, min_stint=20)[:5]
        df = run_monte_carlo(strategies, model, pit_loss=22.0,
                             n_simulations=50, noise_std=0.3)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 5

    def test_mc_sorted_by_mean_time(self, model):
        strategies = generate_one_stop_strategies(57, min_stint=20)[:8]
        df = run_monte_carlo(strategies, model, pit_loss=22.0,
                             n_simulations=50, noise_std=0.3)
        assert list(df["mean_time"]) == sorted(df["mean_time"].tolist())

    def test_win_rates_sum_to_one(self, model):
        strategies = generate_one_stop_strategies(57, min_stint=20)[:5]
        df = run_monte_carlo(strategies, model, pit_loss=22.0,
                             n_simulations=200, noise_std=0.3)
        assert abs(df["win_rate"].sum() - 1.0) < 0.01

    def test_mc_percentiles_ordered(self, model):
        strategies = generate_one_stop_strategies(57, min_stint=20)[:3]
        df = run_monte_carlo(strategies, model, pit_loss=22.0,
                             n_simulations=100, noise_std=0.3)
        for _, row in df.iterrows():
            assert row["p10"] <= row["p50"] <= row["p90"]

    def test_mc_reproducible_with_seed(self, model):
        strategies = generate_one_stop_strategies(57, min_stint=20)[:3]
        kwargs = dict(n_simulations=50, noise_std=0.3, seed=42)
        df1 = run_monte_carlo(strategies, model, 22.0, **kwargs)
        df2 = run_monte_carlo(strategies, model, 22.0, **kwargs)
        pd.testing.assert_frame_equal(
            df1[["strategy", "mean_time"]],
            df2[["strategy", "mean_time"]],
        )

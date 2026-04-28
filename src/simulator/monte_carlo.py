"""
monte_carlo.py — Monte Carlo simulation runner (vectorised).

Instead of calling simulate_race() N times in a Python loop, we:
  1. Pre-compute the deterministic lap-time array for each strategy once.
  2. Generate all noise samples as a (n_laps, n_simulations) matrix in one shot.
  3. Sum along the lap axis → (n_simulations,) total-time vector per strategy.

This eliminates 14M+ Python function calls and cuts runtime from ~90 min → ~10s.
"""

import numpy as np
import pandas as pd
from tqdm import tqdm

from src.simulator.strategy import Strategy, generate_one_stop_strategies
from src.simulator.race_sim import simulate_race
from src.models.tyre_deg import TyreDegModel
from src.utils.config import N_SIMULATIONS, RANDOM_SEED, LAP_TIME_NOISE_STD, RACE_LAPS
from src.utils.logger import get_logger

log = get_logger(__name__)


def _build_lap_time_vector(strategy: Strategy,
                            deg_model: TyreDegModel,
                            pit_loss: float) -> np.ndarray:
    """
    Build a deterministic (n_laps,) array of lap times for a strategy.

    Pit-stop time loss is added as a lump sum to the last lap of each
    non-final stint (same accounting as simulate_race).
    """
    lap_times = []
    available = list(deg_model.models.keys())

    for i, stint in enumerate(strategy.stints):
        compound = stint.compound
        if compound not in deg_model.models:
            compound = "MEDIUM" if "MEDIUM" in deg_model.models else available[0]

        ages = np.arange(1, stint.duration + 1)
        predicted = deg_model.predict(compound, ages).copy()

        if i < len(strategy.stints) - 1:
            predicted[-1] += pit_loss   # in-lap time loss

        lap_times.append(predicted)

    return np.concatenate(lap_times)   # (total_laps,)


def run_monte_carlo(strategies: list,
                    deg_model: TyreDegModel,
                    pit_loss: float,
                    n_simulations: int = N_SIMULATIONS,
                    noise_std: float = LAP_TIME_NOISE_STD,
                    seed: int = RANDOM_SEED) -> pd.DataFrame:
    """
    Run Monte Carlo simulation across all candidate strategies.

    Vectorised: noise is sampled once as a (n_laps, n_sims) matrix and
    added to pre-computed deterministic lap times — no Python loop over
    simulations.

    Returns
    -------
    DataFrame sorted by mean_time ascending with columns:
        strategy, mean_time, std_time, p10, p50, p90,
        pit_count, compounds, win_rate
    """
    rng = np.random.default_rng(seed)
    results = []

    log.info(f"Running Monte Carlo (vectorised): "
             f"{len(strategies)} strategies x {n_simulations} iterations")

    for strat in tqdm(strategies, desc="Simulating strategies"):
        base = _build_lap_time_vector(strat, deg_model, pit_loss)  # (n_laps,)

        if noise_std > 0:
            noise = rng.normal(0.0, noise_std, size=(len(base), n_simulations))
            times = (base[:, None] + noise).sum(axis=0)   # (n_sims,)
        else:
            times = np.full(n_simulations, base.sum())

        results.append({
            "strategy":     str(strat),
            "strategy_obj": strat,
            "mean_time":    float(np.mean(times)),
            "std_time":     float(np.std(times)),
            "p10":          float(np.percentile(times, 10)),
            "p50":          float(np.percentile(times, 50)),
            "p90":          float(np.percentile(times, 90)),
            "pit_count":    strat.pit_count,
            "compounds":    " + ".join(sorted(strat.compounds_used)),
            "_times":       times,
        })

    df = pd.DataFrame(results)
    df = df.sort_values("mean_time").reset_index(drop=True)

    # Win rate: fraction of sims where this strategy beats all others
    all_times = np.stack(df["_times"].values)          # (n_strat, n_sims)
    winner_per_sim = np.argmin(all_times, axis=0)
    win_rates = np.bincount(winner_per_sim, minlength=len(df)) / n_simulations
    df["win_rate"] = win_rates
    df = df.drop(columns=["_times"])

    log.info(f"Best strategy: {df.iloc[0]['strategy']} "
             f"(mean={df.iloc[0]['mean_time']:.1f}s, "
             f"win_rate={df.iloc[0]['win_rate']:.1%})")

    return df


def run_full_analysis(year: int = None,
                      race: str = None,
                      driver: str = None) -> pd.DataFrame:
    """Convenience wrapper: load → clean → fit → MC. Uses config defaults."""
    from src.pipeline.loader import load_session, get_laps, get_pit_stops
    from src.pipeline.cleaner import clean_laps
    from src.pipeline.features import engineer_features
    from src.utils.config import YEAR, RACE, PRIMARY_DRIVER
    from src.models.pit_loss import get_pit_loss

    year   = year   or YEAR
    race   = race   or RACE
    driver = driver or PRIMARY_DRIVER

    session  = load_session(year, race)
    laps     = clean_laps(engineer_features(get_laps(session), total_laps=RACE_LAPS))
    pit_loss = get_pit_loss(get_pit_stops(session))

    deg_model = TyreDegModel()
    deg_model.fit(laps)
    print("\nTyre degradation model summary:")
    print(deg_model.summary().to_string(index=False))

    strategies = generate_one_stop_strategies(RACE_LAPS)
    results = run_monte_carlo(strategies, deg_model, pit_loss)

    print("\nTop 10 strategies by mean race time:")
    print(results.head(10)[
        ["strategy", "mean_time", "std_time", "p10", "p90", "win_rate"]
    ].to_string(index=False))

    return results


if __name__ == "__main__":
    run_full_analysis()


def run_rival_monte_carlo(
    our_strategies: list,
    rival_strategy,
    deg_model,
    pit_loss: float,
    initial_gap: float = 2.0,
    n_simulations: int = N_SIMULATIONS,
    noise_std: float = LAP_TIME_NOISE_STD,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """
    For each candidate strategy, simulate N races against a fixed rival
    and report the probability of finishing ahead.

    Vectorised: rival base times are pre-computed once; noise is sampled
    as a matrix rather than in a Python loop.

    Returns
    -------
    DataFrame sorted by win_rate descending.
    """
    rng = np.random.default_rng(seed)

    rival_base = _build_lap_time_vector(rival_strategy, deg_model, pit_loss)
    n_rival_laps = len(rival_base)

    log.info(
        f"Rival MC (vectorised): {len(our_strategies)} strategies x "
        f"{n_simulations} iters vs {rival_strategy} | gap={initial_gap:+.1f}s"
    )

    results = []

    for our_strat in tqdm(our_strategies, desc="Rival simulations"):
        our_base = _build_lap_time_vector(our_strat, deg_model, pit_loss)
        n_laps   = min(len(our_base), n_rival_laps)
        our_b    = our_base[:n_laps]
        riv_b    = rival_base[:n_laps]

        if noise_std > 0:
            our_noise   = rng.normal(0.0, noise_std, size=(n_laps, n_simulations))
            rival_noise = rng.normal(0.0, noise_std, size=(n_laps, n_simulations))
            our_times   = (our_b[:, None]  + our_noise).sum(axis=0)
            riv_times   = (riv_b[:, None]  + rival_noise).sum(axis=0)
        else:
            our_times = np.full(n_simulations, our_b.sum())
            riv_times = np.full(n_simulations, riv_b.sum())

        final_gaps = initial_gap + riv_times - our_times
        we_won     = final_gaps < 0

        results.append({
            "strategy":       str(our_strat),
            "strategy_obj":   our_strat,
            "win_rate":       round(float(np.mean(we_won)), 4),
            "mean_final_gap": round(float(np.mean(final_gaps)), 3),
            "p10_gap":        round(float(np.percentile(final_gaps, 10)), 3),
            "p50_gap":        round(float(np.percentile(final_gaps, 50)), 3),
            "p90_gap":        round(float(np.percentile(final_gaps, 90)), 3),
            "pit_count":      our_strat.pit_count,
            "compounds":      " + ".join(sorted(our_strat.compounds_used)),
        })

    df = pd.DataFrame(results).sort_values("win_rate", ascending=False).reset_index(drop=True)

    log.info(
        f"Best vs rival: {df.iloc[0]['strategy']} "
        f"(win_rate={df.iloc[0]['win_rate']:.1%}, "
        f"mean_gap={df.iloc[0]['mean_final_gap']:+.1f}s)"
    )
    return df

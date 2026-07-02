"""
rival.py — Rival modelling for undercut / overcut evaluation.

This is what separates a strategy tool from a strategy calculator.

F1 strategy is never about absolute race time — it's always relative.
"Should we pit now to undercut Norris?" is the real question.

Core concepts
─────────────
Gap to rival (seconds)
    How far ahead or behind the rival car we currently are.
    Positive = we are ahead. Negative = we are behind.

Undercut
    We pit before the rival. We sacrifice track position temporarily,
    come out on fresher rubber, and aim to build lap time advantage
    large enough to clear the rival when they pit.

    Undercut works when:
      out-lap pace delta > gap + rival's pace advantage on older tyres

Overcut
    Rival pits first. We stay out on older rubber and aim to hold
    position until they emerge from the pit lane, then build enough
    of a gap that they can't close it before the end of the race.

    Overcut works when:
      our pace on old tyres > rival's out-lap + fresh tyre pace

Safe undercut window
    The lap range where undercut EV is positive AND robust across
    Monte Carlo noise (win rate > 50% of simulations).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.models.tyre_deg import TyreDegModel

log = get_logger(__name__)

# Out-lap penalty: driver pushes hard but cold tyres + pit exit traffic
# Real value: ~1.5–3s slower than a representative flying lap
OUT_LAP_PENALTY = 2.0   # seconds added to predicted lap time on out-lap

# NOTE: pit_loss (passed into every function below) already represents the
# FULL cost of a pit stop versus staying out — pit lane travel time AND
# stationary time combined (see pit_loss.py docstring: "Pit loss = time lost
# versus staying out: approx (pit lane travel time + stationary time) -
# (normal lap delta)"). Do NOT add a separate pit lane delta on top of
# pit_loss here — that would double-count ~19s of penalty per pit stop.


@dataclass
class RivalState:
    """
    Snapshot of a rival car's race state at a given lap.

    Parameters
    ----------
    driver          : Driver code (e.g. "NOR")
    compound        : Current tyre compound
    tyre_age        : Laps on current set
    gap_to_us       : Seconds — positive means rival is ahead of us,
                      negative means rival is behind us
    has_pitted      : Whether the rival has already made their pit stop
    pit_lap_actual  : The lap the rival actually pitted (from FastF1 data),
                      or None if not yet pitted / unknown
    """
    driver: str
    compound: str
    tyre_age: int
    gap_to_us: float          # + = rival ahead, - = rival behind
    has_pitted: bool = False
    pit_lap_actual: int | None = None

    def __repr__(self):
        direction = "ahead" if self.gap_to_us >= 0 else "behind"
        return (f"Rival({self.driver}, {self.compound} age={self.tyre_age}, "
                f"gap={abs(self.gap_to_us):.1f}s {direction})")


@dataclass
class UndercutResult:
    """
    Output of a single undercut evaluation at a given lap.

    gap_after_our_outlap  : Predicted gap to rival after we complete our out-lap.
                             Positive = we are ahead after emerging.
    gap_after_rival_pits  : Predicted gap after rival also pits (end state).
    undercut_works        : Whether we emerge ahead of the rival.
    ev_seconds            : Expected value in seconds (how much we gain vs staying out).
    """
    lap: int
    gap_after_our_outlap: float
    gap_after_rival_pits: float
    undercut_works: bool
    ev_seconds: float


def predict_outlap_time(compound: str,
                         deg_model: "TyreDegModel",
                         noise_std: float = 0.0) -> float:
    """
    Predict out-lap time: fresh tyre lap 1 + out-lap penalty.

    The out-lap is always slower than a representative lap 1 because:
    - Cold tyre temperatures in the pit lane
    - Cautious driving to build temperature safely
    - Pit exit traffic / delta time compliance in some situations
    """
    base = float(deg_model.predict(compound, 1))
    penalty = OUT_LAP_PENALTY
    if noise_std > 0:
        penalty += np.random.normal(0, noise_std * 0.5)
    return base + penalty


def evaluate_undercut(
    lap: int,
    our_compound: str,
    our_tyre_age: int,
    new_compound: str,
    rival: RivalState,
    deg_model: "TyreDegModel",
    pit_loss: float,
    noise_std: float = 0.0,
) -> UndercutResult:
    """
    Evaluate whether undercutting the rival on this lap is positive EV.

    Logic:
    1. We pit this lap → lose pit_loss seconds.
    2. We complete our out-lap on new_compound → outlap time.
    3. Rival completes one more lap on their current (older) tyre.
    4. We compute our track position relative to rival after this exchange.
    5. Then rival pits → we compute final gap.

    Parameters
    ----------
    lap           : Current race lap
    our_compound  : Our current tyre compound
    our_tyre_age  : Our current tyre age
    new_compound  : Compound we'd fit if we pit now
    rival         : RivalState at this lap
    deg_model     : Fitted TyreDegModel
    pit_loss      : Pit stop stationary time loss (seconds)
    noise_std     : Monte Carlo noise std dev

    Returns
    -------
    UndercutResult with gap projections and EV.
    """
    # --- Step 1: We pit, rival stays out ---
    # We lose exactly pit_loss seconds relative to rival (pit_loss already
    # represents the full delta of stopping vs. staying out for one lap —
    # see pit_loss.py). Steps 2-3 below separately account for the ongoing
    # pace differential via lap-time deltas, so step 1 must NOT also mix in
    # an absolute lap time here (that was double-counting pace on top of
    # the stop cost, since pit_loss is already a delta, not a raw lap time).
    gap_after_pit = rival.gap_to_us + pit_loss
    # gap_after_pit: positive = rival still ahead after our pit

    # --- Step 2: Our out-lap vs rival's next lap ---
    our_outlap = predict_outlap_time(new_compound, deg_model, noise_std)
    rival_next_lap = float(deg_model.predict(rival.compound, rival.tyre_age + 1))
    if noise_std > 0:
        rival_next_lap += np.random.normal(0, noise_std)

    # Gap after our out-lap:
    gap_after_outlap = gap_after_pit + (our_outlap - rival_next_lap)
    # If gap_after_outlap < 0 we are now ahead of the rival (undercut succeeded)

    # --- Step 3: Project to when rival pits (assume they pit ~2 laps after us) ---
    # On fresher tyres we should be faster; rival's tyres are 2 laps older
    our_flying_lap = float(deg_model.predict(new_compound, 2))
    rival_old_lap = float(deg_model.predict(rival.compound, rival.tyre_age + 2))
    pace_delta_per_lap = rival_old_lap - our_flying_lap  # + means we are faster

    # Over ~2 laps before rival pits, we gain/lose this delta
    gap_after_rival_pits = gap_after_outlap - (2 * pace_delta_per_lap)

    # EV: how much better off are we vs staying out?
    # Staying out = gap stays at rival.gap_to_us (approx)
    ev = rival.gap_to_us - gap_after_rival_pits  # + = we improved position

    return UndercutResult(
        lap=lap,
        gap_after_our_outlap=round(gap_after_outlap, 3),
        gap_after_rival_pits=round(gap_after_rival_pits, 3),
        undercut_works=(gap_after_outlap < 0),
        ev_seconds=round(ev, 3),
    )


def evaluate_overcut(
    lap: int,
    our_compound: str,
    our_tyre_age: int,
    new_compound: str,
    rival: RivalState,
    deg_model: "TyreDegModel",
    pit_loss: float,
    noise_std: float = 0.0,
) -> dict:
    """
    Evaluate whether overcutting (staying out while rival pits) is +EV.

    Overcut logic:
    1. Rival pits this lap → loses pit_loss + pit lane delta.
    2. We stay out on old tyres → complete our lap.
    3. Rival completes out-lap on fresh rubber.
    4. We compute gap after this exchange.
    5. If we're ahead, can we hold it? (Pace delta on remaining laps matters)

    Returns a dict with gap projections and sustainability assessment.
    """
    # Rival pits this lap → loses exactly pit_loss seconds relative to us
    # (same reasoning as evaluate_undercut step 1 — pit_loss is already a
    # delta, not a raw lap time, so it must not be combined with one here).
    gap_after_rival_pit = rival.gap_to_us - pit_loss
    # We want gap_after_rival_pit < 0 (we're ahead after they emerge)

    # Rival's out-lap on fresh tyres
    rival_outlap = predict_outlap_time(new_compound, deg_model, noise_std)

    # Our next lap (one lap older)
    our_next_lap = float(deg_model.predict(our_compound, our_tyre_age + 1))
    if noise_std > 0:
        our_next_lap += np.random.normal(0, noise_std)

    gap_after_exchange = gap_after_rival_pit + (our_next_lap - rival_outlap)

    # Sustainability: fresh rival tyres will be faster than our old ones
    rival_flying = float(deg_model.predict(new_compound, 2))
    our_deg_pace = float(deg_model.predict(our_compound, our_tyre_age + 2))
    pace_deficit_per_lap = our_deg_pace - rival_flying  # + means we're slower

    # Laps we can hold position before they close the gap
    if pace_deficit_per_lap > 0 and gap_after_exchange < 0:
        laps_sustainable = abs(gap_after_exchange) / pace_deficit_per_lap
    else:
        laps_sustainable = 999.0  # we're faster, we hold forever

    overcut_works = gap_after_exchange < 0

    # EV: how much better off are we (in gap terms) vs pitting immediately.
    # Mirrors the undercut EV formula for direct comparability: positive EV
    # means staying out gained us position/time relative to the starting gap.
    ev = rival.gap_to_us - gap_after_exchange

    return {
        "lap": lap,
        "gap_after_rival_pit": round(gap_after_rival_pit, 3),
        "gap_after_exchange": round(gap_after_exchange, 3),
        "overcut_works": overcut_works,
        "ev_seconds": round(ev, 3),
        "pace_deficit_per_lap": round(pace_deficit_per_lap, 3),
        "laps_sustainable": round(min(laps_sustainable, 50.0), 1),
    }


def scan_undercut_window(
    from_lap: int,
    to_lap: int,
    our_compound: str,
    our_tyre_age_at_from_lap: int,
    new_compound: str,
    rival: RivalState,
    deg_model: "TyreDegModel",
    pit_loss: float,
    n_simulations: int = 200,
    noise_std: float = 0.3,
) -> pd.DataFrame:
    """
    Monte Carlo scan of undercut EV across a range of laps.

    For each candidate pit lap in [from_lap, to_lap], runs n_simulations
    of the undercut evaluation with lap time noise, then reports:
      - mean EV (seconds gained vs staying out)
      - P10 / P50 / P90 EV
      - win_rate (fraction of simulations where undercut_works=True)
      - recommend (True when win_rate >= 0.5 AND mean_ev > 0)

    Parameters
    ----------
    from_lap                  : First candidate pit lap to evaluate
    to_lap                    : Last candidate pit lap
    our_compound              : Our current tyre compound
    our_tyre_age_at_from_lap  : Our tyre age at from_lap (increments each lap)
    new_compound              : Compound we'd fit if we pit
    rival                     : RivalState (gap, compound, tyre_age at from_lap)
    deg_model                 : Fitted TyreDegModel
    pit_loss                  : Pit stop time loss (seconds)
    n_simulations             : MC iterations per lap
    noise_std                 : Lap time noise std dev

    Returns
    -------
    DataFrame with one row per candidate lap.
    """
    rows = []
    rival_tyre_age = rival.tyre_age

    for offset, lap in enumerate(range(from_lap, to_lap + 1)):
        our_age = our_tyre_age_at_from_lap + offset
        rival_age = rival_tyre_age + offset

        rival_at_lap = RivalState(
            driver=rival.driver,
            compound=rival.compound,
            tyre_age=rival_age,
            gap_to_us=rival.gap_to_us,  # simplified: hold gap constant
            has_pitted=rival.has_pitted,
        )

        ev_samples = []
        works_count = 0

        for _ in range(n_simulations):
            result = evaluate_undercut(
                lap=lap,
                our_compound=our_compound,
                our_tyre_age=our_age,
                new_compound=new_compound,
                rival=rival_at_lap,
                deg_model=deg_model,
                pit_loss=pit_loss,
                noise_std=noise_std,
            )
            ev_samples.append(result.ev_seconds)
            if result.undercut_works:
                works_count += 1

        ev_arr = np.array(ev_samples)
        win_rate = works_count / n_simulations

        rows.append({
            "lap":        lap,
            "our_age":    our_age,
            "rival_age":  rival_age,
            "mean_ev":    round(float(np.mean(ev_arr)), 3),
            "p10_ev":     round(float(np.percentile(ev_arr, 10)), 3),
            "p50_ev":     round(float(np.percentile(ev_arr, 50)), 3),
            "p90_ev":     round(float(np.percentile(ev_arr, 90)), 3),
            "win_rate":   round(win_rate, 3),
            "recommend":  win_rate >= 0.5 and float(np.mean(ev_arr)) > 0,
        })

    df = pd.DataFrame(rows)
    log.info(
        f"Undercut scan {from_lap}–{to_lap} vs {rival.driver}: "
        f"{df['recommend'].sum()} recommended laps"
    )
    return df


def scan_overcut_window(
    from_lap: int,
    to_lap: int,
    our_compound: str,
    our_tyre_age_at_from_lap: int,
    new_compound: str,
    rival: RivalState,
    deg_model: "TyreDegModel",
    pit_loss: float,
    n_simulations: int = 200,
    noise_std: float = 0.3,
) -> pd.DataFrame:
    """
    Monte Carlo scan of overcut EV across a range of assumed rival pit laps.

    Mirrors scan_undercut_window(), but evaluates the opposite strategy:
    we stay out while the rival pits on each candidate lap. Our tyre age
    increases with each lap we stay out; the rival's resets to 1 (fresh)
    the lap after they pit.

    For each candidate rival pit lap in [from_lap, to_lap], runs
    n_simulations of the overcut evaluation with lap time noise, then
    reports the same schema as scan_undercut_window() so the two can be
    directly compared side by side in the UI:
      - mean_ev, p10_ev, p50_ev, p90_ev  (seconds gained vs pitting now)
      - win_rate  (fraction of sims where overcut_works=True)
      - recommend (win_rate >= 0.5 AND mean_ev > 0)

    Parameters
    ----------
    from_lap                  : Earliest lap we assume the rival might pit
    to_lap                    : Latest lap we assume the rival might pit
    our_compound              : Our current tyre compound (the one we hold)
    our_tyre_age_at_from_lap  : Our tyre age at from_lap (increments each lap)
    new_compound              : Compound the RIVAL is assumed to fit
                                 (used to model their out-lap pace)
    rival                     : RivalState (gap, compound, tyre_age at from_lap)
    deg_model                 : Fitted TyreDegModel
    pit_loss                  : Pit stop time loss (seconds) — rival's cost
    n_simulations             : MC iterations per lap
    noise_std                 : Lap time noise std dev

    Returns
    -------
    DataFrame with one row per candidate rival pit lap.
    """
    rows = []
    rival_tyre_age = rival.tyre_age

    for offset, lap in enumerate(range(from_lap, to_lap + 1)):
        our_age   = our_tyre_age_at_from_lap + offset
        rival_age = rival_tyre_age + offset

        rival_at_lap = RivalState(
            driver=rival.driver,
            compound=rival.compound,
            tyre_age=rival_age,
            gap_to_us=rival.gap_to_us,  # simplified: hold gap constant until this lap
            has_pitted=rival.has_pitted,
        )

        ev_samples = []
        works_count = 0

        for _ in range(n_simulations):
            result = evaluate_overcut(
                lap=lap,
                our_compound=our_compound,
                our_tyre_age=our_age,
                new_compound=new_compound,
                rival=rival_at_lap,
                deg_model=deg_model,
                pit_loss=pit_loss,
                noise_std=noise_std,
            )
            ev_samples.append(result["ev_seconds"])
            if result["overcut_works"]:
                works_count += 1

        ev_arr = np.array(ev_samples)
        win_rate = works_count / n_simulations

        rows.append({
            "lap":        lap,
            "our_age":    our_age,
            "rival_age":  rival_age,
            "mean_ev":    round(float(np.mean(ev_arr)), 3),
            "p10_ev":     round(float(np.percentile(ev_arr, 10)), 3),
            "p50_ev":     round(float(np.percentile(ev_arr, 50)), 3),
            "p90_ev":     round(float(np.percentile(ev_arr, 90)), 3),
            "win_rate":   round(win_rate, 3),
            "recommend":  win_rate >= 0.5 and float(np.mean(ev_arr)) > 0,
        })

    df = pd.DataFrame(rows)
    log.info(
        f"Overcut scan {from_lap}–{to_lap} vs {rival.driver}: "
        f"{df['recommend'].sum()} favourable laps to stay out"
    )
    return df


def build_rival_from_laps(
    laps: pd.DataFrame,
    rival_driver: str,
    reference_lap: int,
    our_lap_time_at_reference: float,
) -> RivalState | None:
    """
    Construct a RivalState from real FastF1 lap data at a specific race lap.

    Parameters
    ----------
    laps                         : Full race laps DataFrame (all drivers)
    rival_driver                 : Driver code of the rival
    reference_lap                : Race lap number to snapshot
    our_lap_time_at_reference    : Our cumulative time at this lap (for gap calc)

    Returns
    -------
    RivalState, or None if rival data not available at this lap.
    """
    rival_laps = laps[
        (laps["Driver"] == rival_driver) &
        (laps["LapNumber"] <= reference_lap)
    ].copy()

    if rival_laps.empty:
        log.warning(f"No lap data found for rival {rival_driver} up to lap {reference_lap}")
        return None

    latest = rival_laps.iloc[-1]

    # Estimate gap: difference in cumulative lap times (rough approximation)
    rival_cumulative = rival_laps["LapTimeSec"].sum()
    gap = our_lap_time_at_reference - rival_cumulative  # + = rival is ahead

    has_pitted = rival_laps["PitInTime"].notna().any()
    pit_lap_row = rival_laps[rival_laps["PitInTime"].notna()]
    pit_lap = int(pit_lap_row["LapNumber"].iloc[-1]) if not pit_lap_row.empty else None

    return RivalState(
        driver=rival_driver,
        compound=str(latest.get("Compound", "MEDIUM")),
        tyre_age=int(latest.get("TyreLife", 1)),
        gap_to_us=round(float(gap), 3),
        has_pitted=has_pitted,
        pit_lap_actual=pit_lap,
    )

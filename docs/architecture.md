# Architecture — F1 Strategy AI

## System Overview

The project is a four-stage data pipeline with a simulation and rival-engine layer on top:

```
FastF1 API
    │
    ▼
[pipeline/loader.py]       ← Session loading, caching, live race schedule (auto-updates
    │                         to the latest completed season), weather, final classification
    ▼
[pipeline/cleaner.py]      ← Remove SC/VSC laps, inaccurate laps, per-compound outlier
    │                         removal — vectorised (groupby().transform(), not apply())
    ▼
[pipeline/features.py]     ← Tyre age, stint number, fuel correction, DegDelta —
    │                         also vectorised, same reasoning
    ▼
[models/tyre_deg.py]       ← 3-phase piecewise-linear degradation model (pwlf),
[models/pit_loss.py]         cliff estimation, driver-weighted fitting,
    │                         track-temperature scaling
    ▼
[simulator/strategy.py]    ← Strategy & Stint dataclasses, generator functions
[simulator/race_sim.py]    ← Deterministic race simulation, backtest reconstruction
[simulator/monte_carlo.py] ← Vectorised N-iteration Monte Carlo runner
[simulator/rival.py]       ← Undercut AND overcut EV scanning, head-to-head MC
    │
    ▼
[visualisation/]           ← Dashboard, degradation/strategy/rival plots

React Mission Control
    │
    ├── `frontend/src/api.ts`      ← typed FastAPI request/result contracts
    ├── `frontend/src/App.tsx`     ← session state, persistence, tabs, replay
    └── `frontend/src/Charts.tsx`  ← SVG analytical charts
```

---

## Key Design Decisions

### Why piecewise-linear regression instead of a polynomial for tyre degradation?

The piecewise model approximates tyre-age effects with bedding, plateau, and
cliff segments. A polynomial is smooth and cannot represent a discontinuous
change in slope.

`TyreDegModel` fits 3 linear segments via `pwlf.PiecewiseLinFit`, with breakpoints
optimised jointly. The final internal breakpoint is a candidate cliff lap,
subject to slope and data-boundary checks. Interval outputs are experimental;
their statistical coverage has not been validated.

Full reasoning, including the polynomial's specific failure modes, is in
[`docs/decisions.md`](decisions.md).

### Why driver-weighted fitting instead of filtering to one driver?

Filtering to one driver reduces the available fitting data.
`TyreDegModel.fit(laps, driver=X, driver_weight=4.0)` increases the selected
driver's fitting weights while retaining other drivers' laps. A compound with
too few laps falls back to fewer segments or is omitted. This weighting
is a modelling choice; its predictive benefit still needs validation.

### Why per-compound models instead of one joint model?

Compound type has radically different baseline and slope characteristics. Separate
models give each compound its own curve shape with no shared constraint — there's
no reason SOFT and HARD should share a functional form.

### Why vectorised outlier removal (`transform`) instead of `groupby().apply()`?

`groupby().transform()` returns group statistics aligned with the original
rows. The cleaner uses those statistics to select rows, and feature
engineering adds stint deltas without reconstructing the grouped table.

### Why undercut *and* overcut, not just undercut?

`rival.py` scans both directions against a configurable rival's compound,
tyre age, and gap, reporting simulated EV, P10–P90, and win rate. The scans
use different evaluation horizons, so their EV values and recommendations
need validation before they can support a direct strategic comparison.

### Why Monte Carlo over analytical optimisation?

Monte Carlo samples the configured lap-time noise to produce simulated
race-time percentiles and win rates. These describe variation under the
model assumptions; they are not calibrated probabilities of real outcomes
or confidence intervals for the best pit lap.

### Why does the season selector auto-update?

`get_latest_available_year()` checks the current calendar year for completed
races (filtering out any event with a future `EventDate`) and falls back to the
previous year if the new season hasn't started yet. The dashboard's year range
is built from this at runtime — there's no hardcoded upper bound to remember to
bump every January.

### Caching

FastF1's built-in cache (`Cache.enable_cache()`) stores downloaded sessions
locally at `data/cache/`. Cached requests can reduce subsequent downloads for the same session.

### Browser persistence and replay

The primary React client keeps the active simulation and UI selections in
browser `localStorage`. The active result is restored on refresh, while an
explicit reset removes only that current-run snapshot. Separate saved-run
records support loading, deleting, clearing, and comparing multiple simulation
results locally. This layer is deliberately browser-local; it does not change
the Python engine or create a server-side account/sync model.

The Overview Track Map consumes the simulation's lap-time trace and FastF1
circuit points. A requestAnimationFrame clock drives Play/Pause, seek, restart,
and speed control; each driver node is positioned by lap-time interpolation
along the circuit path. The map falls back gracefully when geometry or replay
data is unavailable.

---

## Module Boundaries

| Module | Inputs | Outputs | Side Effects |
|--------|--------|---------|--------------|
| `loader.py` | year, race, session | `session`, `laps`, `pit_stops`, weather, classification | Writes to `data/cache/` |
| `cleaner.py` | raw `laps` DataFrame | cleaned `laps` (all original columns preserved) | None |
| `features.py` | cleaned `laps` | feature-enriched `laps` (all columns preserved) | None |
| `tyre_deg.py` | enriched `laps`, optional `driver` | fitted `TyreDegModel` | None |
| `pit_loss.py` | `pit_stops` | float (seconds) | None |
| `race_sim.py` | `Strategy`, models | result dict (incl. backtest reconstruction) | None |
| `monte_carlo.py` | strategies, models | results DataFrame | None |
| `rival.py` | `RivalState`, models | undercut/overcut scan DataFrames | None |
| `visualisation/` | results | Streamlit widgets, optional PNG files | Writes to `outputs/` if `save=True` |

---

## Data Flow: Column Glossary

| Column | Added by | Description |
|--------|----------|--------------|
| `LapTimeSec` | `loader.get_laps()` | Lap time as float seconds |
| `TyreAge` | `features.add_tyre_age()` | Laps on current tyre set |
| `StintNumber` | `features.add_stint_number()` | Stint index (1, 2, 3…) |
| `FuelCorrectedLapTime` | `features.add_fuel_corrected_lap_time()` | Lap time minus ~0.05s/lap fuel effect |
| `DegDelta` | `features.add_deg_delta()` | Lap time delta from first lap of stint (vectorised `transform("first")`) |

---

## Configuration

All tuneable parameters live in `src/utils/config.py`. Key parameters:

- `N_SIMULATIONS` — Monte Carlo iterations (default 1000, adjustable 100–2000 via dashboard slider)
- `LAP_TIME_NOISE_STD` — lap time uncertainty in seconds (default 0.3)
- `DEG_MIN_LAPS_FULL` / `DEG_MIN_LAPS_FALLBACK` — piecewise fit data thresholds (12 / 6 laps)
- `DEG_CLIFF_THRESHOLD` — minimum slope (s/lap) to declare a segment a cliff (0.12)
- `PIT_LOSS` — per-team pit stop time loss lookup table

Season, race, and driver are **not** in config — they're selected live in the
dashboard sidebar, sourced from FastF1's event schedule at runtime.

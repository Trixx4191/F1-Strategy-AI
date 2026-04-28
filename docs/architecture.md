# Architecture — F1 Strategy AI

## System Overview

The project is structured as a four-stage pipeline with a simulation layer on top:

```
FastF1 API
    │
    ▼
[pipeline/loader.py]       ← Pull session data, cache locally
    │
    ▼
[pipeline/cleaner.py]      ← Remove SC laps, pit laps, outliers
    │
    ▼
[pipeline/features.py]     ← Tyre age, stint number, fuel correction, DegDelta
    │
    ▼
[models/tyre_deg.py]       ← Per-compound polynomial regression
[models/pit_loss.py]       ← Mean pit stop time from race data
[models/lap_time.py]       ← Full-race lap time distribution
    │
    ▼
[simulator/strategy.py]    ← Strategy & Stint dataclasses, generator functions
[simulator/race_sim.py]    ← Deterministic race simulation
[simulator/monte_carlo.py] ← N-iteration Monte Carlo runner
    │
    ▼
[visualisation/]           ← Charts, dashboard
```

---

## Key Design Decisions

### Why polynomial regression for tyre degradation?

A degree-2 polynomial (`TyreDegModel`, `DEG_POLY_DEGREE=2`) provides a compact
approximation to age-dependent lap times. It cannot represent an abrupt
change in slope, and its extrapolation and predictive accuracy need validation.

Alternative model families include linear regression, higher-degree
polynomials, piecewise regression, and Gaussian processes.

### Why per-compound models instead of one joint model?

Compound type is a categorical variable with radically different baseline + slope characteristics. A joint model with a compound dummy variable forces shared functional form. Separate models give each compound its own polynomial shape with no shared constraint, which is correct — there's no reason SOFT and HARD should have the same degradation shape.

### Why Z-score per compound for outlier removal?

Outliers (off-track excursions, cool-down laps, VSC periods with `IsAccurate=False` but wrong TrackStatus) would bias the regression. Z-score per compound group rather than globally avoids removing valid laps from slower compounds.

### Why Monte Carlo over analytical optimisation?

Monte Carlo samples the configured lap-time noise to produce simulated
race-time percentiles and win rates. These describe variation under the
model assumptions; they are not calibrated probabilities of real outcomes
or confidence intervals for the best pit lap.

### Caching

FastF1's built-in cache (`Cache.enable_cache()`) stores downloaded sessions as Parquet locally. This is set to `data/cache/`. Cached requests can reduce subsequent downloads for the same session.

---

## Module Boundaries

| Module | Inputs | Outputs | Side Effects |
|--------|--------|---------|--------------|
| `loader.py` | year, race, session | `session`, `laps`, `pit_stops` DataFrames | Writes to `data/cache/` |
| `cleaner.py` | raw `laps` DataFrame | cleaned `laps` | None |
| `features.py` | cleaned `laps` | feature-enriched `laps` | None |
| `tyre_deg.py` | enriched `laps` | fitted `TyreDegModel` | None |
| `pit_loss.py` | `pit_stops` | float (seconds) | None |
| `race_sim.py` | `Strategy`, models | result dict | None |
| `monte_carlo.py` | strategies, models | results DataFrame | None |
| `visualisation/` | results | PNG files | Writes to `outputs/` |

---

## Data Flow: Column Glossary

Key columns added at each pipeline stage:

| Column | Added by | Description |
|--------|----------|-------------|
| `LapTimeSec` | `loader.get_laps()` | Lap time as float seconds |
| `TyreAge` | `features.add_tyre_age()` | Laps on current tyre set |
| `StintNumber` | `features.add_stint_number()` | Stint index (1, 2, 3…) |
| `FuelCorrectedLapTime` | `features.add_fuel_corrected_lap_time()` | Lap time minus ~0.05s/lap fuel effect |
| `DegDelta` | `features.add_deg_delta()` | Lap time delta from first lap of stint |

---

## Configuration

All tuneable parameters live in `src/utils/config.py`. No magic numbers scattered in code.

Key parameters:
- `YEAR`, `RACE`, `DRIVER` — target race/driver
- `DEG_POLY_DEGREE` — regression degree (default 2)
- `N_SIMULATIONS` — Monte Carlo iterations (default 1000, 200 for fast dev)
- `LAP_TIME_NOISE_STD` — lap time uncertainty in seconds (default 0.3)
- `PIT_LOSS` — per-team pit stop time loss lookup table

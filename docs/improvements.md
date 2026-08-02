# Improvements Roadmap

Ordered by impact-to-effort ratio. Items at the top are the highest-value additions.

---

## Implemented capabilities

These capabilities are implemented and remain open to validation and improvement.

- **Rival modelling (undercut *and* overcut)** — `rival.py` scans both directions
  against a configurable rival, with EV, P10–P90, and win rate per candidate lap,
  displayed side by side. The scans use different evaluation horizons;
  direct comparison of their EV values still needs validation.
- **Tyre cliff detection** — replaced the polynomial with a 3-phase piecewise-linear
  model with a fitted cliff estimate. Interval outputs are experimental
  and their statistical coverage has not been validated.
- **Driver-specific deg model** — implemented as weighted-blend fitting (`sample_weight`
  up-weighting), not pure filtering — see `docs/decisions.md` for why filtering alone
  was rejected.
- **CI pipeline** — GitHub Actions automates project checks.
- **Results export and backtesting** — Backtest tab reconstructs the actual driver
  strategy from FastF1 stint data and compares deterministic race time against the
  AI-optimal strategy.
- **Track temperature / weather sensitivity** — `TyreDegModel.set_track_temp()` scales
  degradation excess against live session weather data.
- **Dynamic season range** — the dashboard's year selector auto-detects the latest
  completed season via `get_latest_available_year()`; no manual yearly bump needed.
- **Dockerfile / docker-compose** — one-command local run.

---

## 🔴 High Impact — Do These Next

### 1. Safety Car Monte Carlo layer
**What**: Sample SC events probabilistically per Monte Carlo iteration and
evaluate whether pitting under an SC improves the simulated strategy.

**Why it matters**: The main strategy simulation does not currently apply
safety-car effects. `lap_time.py` defines a separate expected-value helper,
but the main simulator does not call it.

**How**: Extract historical SC lap frequency from FastF1 `TrackStatus` per circuit.
Sample SC occurrence per MC iteration. When one fires within N laps of a planned
pit, allow the simulation to bring the stop forward.

---

### 2. Circuit-cluster multi-race training
**What**: Fit the degradation model on laps pooled across circuits with similar
degradation character (e.g. Bahrain + Qatar + Abu Dhabi), not just the target race.

**Why it matters**: Pooling races could increase available training data,
but transfer across circuits needs evaluation. It could also support
a mixed-effects driver model with random intercepts and slopes.

**How**: `loader.py` already supports arbitrary `year`/`race` inputs — add a
`batch_load_sessions()` function and a `circuit_offset` fixed-effect feature so the
core curve shape transfers across circuits while the intercept shifts per track.

---

### 3. Strategy history tab
**What**: Pit lap heatmap by year for the selected circuit — x-axis lap number,
y-axis year, colour = number of drivers who pitted that lap. Overlay the winning
strategy each year.

**Why it matters**: Historical pit choices would provide context for the
simulated recommendations, while remaining separate from evidence of accuracy.

**How**: Pull all historical years for the circuit via `get_race_schedule()` per
year, extract pit laps per driver via `get_pit_stops()`, render as a `seaborn` heatmap.

---

## 🟡 Medium Impact — Good Portfolio Additions

### 4. Multi-car rival scanning
**What**: Currently `rival.py` evaluates one rival at a time. Extend to scan
multiple simultaneous rivals (e.g. a 3-way DRS train).

### 5. Telemetry analysis module
**What**: Track map (lat/lon from FastF1 position data), speed/brake/throttle
traces, delta-to-reference-lap, sector time breakdown. A different skill
demonstration than the strategy engine — signal processing and time alignment
rather than Monte Carlo.

**Status**: Scoped as the next major module — see project README roadmap.

### 6. Mixed-effects driver modelling
**What**: Once circuit-cluster training (item 2) provides enough per-driver data,
replace the current weighted-blend approximation with a proper mixed-effects
model — random intercept/slope per driver, shrunk toward the fleet mean when
data is sparse, converging to the driver-specific value as data accumulates.

**Why it matters**: The weighted-blend approach is a reasonable approximation
given single-race data constraints, but a true mixed-effects model handles the
sparse-vs-abundant-data tradeoff statistically rather than via a fixed weight
multiplier.

---

## 🟢 Lower Impact — Nice-to-Have

### 7. Jupyter notebook EDA
**Status**: Directory created (`notebooks/`) but notebooks not yet written.

- `01_data_exploration.ipynb` — lap time distributions, compound usage by team, pit timing scatter
- `02_tyre_deg_modelling.ipynb` — interactive piecewise fitting, residual plots, cliff detection walkthrough
- `03_strategy_simulation.ipynb` — run MC interactively, visualise confidence intervals
- `04_results_analysis.ipynb` — compare simulated result vs actual race result (extends the backtest tab)

### 8. Streamlit Cloud / Fly.io public deployment
Deploy the dashboard publicly so it can be demoed without cloning. Requires
handling the FastF1 cache in a cloud-safe way — either a persistent volume
(Fly.io) or accepting slower first-loads per session (Streamlit Cloud's
ephemeral filesystem).

### 9. Grounded natural-language Q&A ("Race Engineer")
**What**: Answer questions like "why were we slower in sector 2" by querying
telemetry (item 5), the degradation model, and weather data, and producing a
report where every claim traces to a specific retrieved number — not a chatbot
wrapper. Depends on item 5 existing first, since it needs sector-level data to
query against.

**Status**: Deliberately scoped last — needs the telemetry data layer in place
to have anything real to ground its answers in.

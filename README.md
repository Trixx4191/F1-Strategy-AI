# 🏎 F1 Strategy AI — Monte Carlo Pit Stop & Rival Strategy Engine

> **F1 timing data. Tyre-degradation modelling. Monte Carlo strategy exploration.**
> A full-stack race strategy simulator built on FastF1 data, a 3-phase piecewise degradation model, vectorised Monte Carlo simulation, and an undercut/overcut rival engine — with a live Streamlit dashboard inspired by F1 broadcast telemetry design.

[![Python](https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python)](https://python.org)
[![FastF1](https://img.shields.io/badge/FastF1-3.3-red?style=flat-square)](https://theoehrly.github.io/Fast-F1/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32-ff4b4b?style=flat-square&logo=streamlit)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

---

## What This Does

F1 race strategy is a real-time optimisation problem under uncertainty: noisy tyre degradation, an opponent whose next move you don't control, and thousands of possible strategy combinations, all under a hard time budget.

This project builds a strategy decision-support system from the data up — not a toy pit-stop calculator, but a system that models the physics of tyre wear, the economics of a pit stop, and the game-theoretic question of *when to fight for track position*:

- **Loads real race data** via FastF1 — lap times, tyre compounds, pit stops, weather, final classification — for **any season 2018–2024**, not a hardcoded race
- **Cleans and engineers features** — removes SC/VSC laps, inaccurate laps, fuel-corrects lap times, tracks stint-relative degradation
- **Fits a 3-phase piecewise-linear degradation model** per compound (bedding → plateau → cliff), with fitted cliff-breakpoint estimates
- **Scales degradation using session track temperature**
- **Generates 1-stop and 2-stop strategy candidates** within compound and minimum-stint constraints, then evaluates them with vectorised Monte Carlo
- **Explores undercut and overcut scenarios** against a configurable rival
- **Backtests** the highest-ranked simulated strategy against what the driver actually did, using real stint data
- **Visualises everything** in an interactive dark-mode dashboard with an F1-app-inspired timing tower and weather strip

---

## Architecture

```
FastF1 API
    │
    ▼
[pipeline/loader.py]       ← Session loading, caching, live race schedule/laps,
    │                         weather, final classification — no hardcoded season data
    ▼
[pipeline/cleaner.py]      ← Remove SC/VSC laps, inaccurate laps, per-compound
    │                         outlier removal (vectorised, not per-group apply())
    ▼
[pipeline/features.py]     ← Tyre age, stint number, fuel correction, DegDelta
    │                         (vectorised transform — no groupby().apply() column loss)
    ▼
[models/tyre_deg.py]       ← 3-phase piecewise-linear degradation model (pwlf),
[models/pit_loss.py]         cliff estimates, driver-weighted fitting,
    │                         track temperature scaling
    ▼
[simulator/strategy.py]    ← Strategy & Stint dataclasses, generator functions
[simulator/race_sim.py]    ← Deterministic race simulation, backtest reconstruction
[simulator/monte_carlo.py] ← Vectorised N-iteration Monte Carlo runner
[simulator/rival.py]       ← Undercut AND overcut EV scanning against a rival
    │
    ▼
[visualisation/]           ← Dashboard, degradation/strategy/rival plots
```

```
f1-strategy-ai/
├── src/
│   ├── pipeline/
│   │   ├── loader.py        # Session loading, live schedule, weather, classification
│   │   ├── cleaner.py       # SC laps, inaccurate laps, vectorised outlier removal
│   │   └── features.py      # Fuel correction, tyre age, vectorised stint deltas
│   ├── models/
│   │   ├── tyre_deg.py      # 3-phase piecewise model, cliff detection, temp scaling
│   │   └── pit_loss.py      # Data-driven pit stop time loss
│   ├── simulator/
│   │   ├── strategy.py      # Strategy / Stint dataclasses + generation
│   │   ├── race_sim.py      # Deterministic race simulation + backtest support
│   │   ├── monte_carlo.py   # Vectorised MC engine (NumPy matrix ops)
│   │   └── rival.py         # Undercut / overcut EV scanning, H2H Monte Carlo
│   ├── visualisation/
│   │   ├── dashboard.py     # Streamlit app (main entry point)
│   │   ├── tyre_plots.py    # Piecewise degradation curves, cliff markers
│   │   ├── strategy_plots.py  # Comparison bars, lap traces, undercut heatmap
│   │   └── rival_plots.py   # Undercut/overcut EV timeline, H2H, comparison chart
│   └── utils/
│       ├── config.py        # Central config
│       └── logger.py        # Structured logging
├── tests/                   # Pipeline, model, simulation, and rival tests
│   ├── test_pipeline.py
│   ├── test_tyre_deg.py
│   ├── test_simulator.py
│   └── test_rival.py
├── docs/
│   ├── architecture.md
│   ├── decisions.md         # Modelling and pipeline design choices
│   ├── model_notes.md
│   └── improvements.md
├── .github/workflows/test.yml  # CI — runs full suite on push/PR
├── Dockerfile
├── docker-compose.yml
└── data/cache/               # FastF1 HTTP cache (auto-populated)
```

---

## Technical Highlights

### 3-Phase Piecewise Tyre Model — Not a Polynomial

Real tyre degradation has three physically distinct phases: a bedding phase (new rubber, lap times can *improve*), a plateau (roughly linear wear), and a cliff (abrupt breakdown). A polynomial forces a single smooth curve across all three — it can't represent a phase transition.

This model fits piecewise-linear segments (via `pwlf`) with the breakpoints optimised jointly:

```
Bedding  → laps 1–B₁    (often slightly negative slope)
Plateau  → laps B₁–B₂   (roughly linear degradation)
Cliff    → laps B₂+     (steep slope increase)
```

The fitted cliff lap `B₂` is exposed when the final segment passes the slope and boundary checks:

```python
model.cliff_lap("SOFT")   # fitted breakpoint, or None
```

### Driver-Weighted Fitting, Not Pure Filtering

The selected driver's laps receive a configurable fitting weight (default 4×), while other drivers' laps remain in the dataset. Sparse compounds use a simpler 2-segment fit or are skipped.

### Track Temperature Scaling

Session track temperature scales predicted degradation above baseline pace. The scale factor is clamped; this is a modelling assumption rather than a calibrated weather model.

### Undercut *and* Overcut, Side by Side

The engine scans candidate laps for a configurable rival and reports gap-change scores, percentiles, and simulated success rates. These are short-horizon projections; the two scans do not represent the same complete pit-stop exchange.

```
EV(lap_n) = gap_to_us − gap_after_strategy(lap_n)
```

### Vectorised Monte Carlo

The simulation engine pre-computes deterministic lap-time vectors per strategy, then generates noise as a `(n_laps × n_simulations)` NumPy matrix in one shot — no per-iteration Python loop.

```python
base  = build_lap_time_vector(strategy, deg_model, pit_loss)   # (n_laps,)
noise = rng.normal(0, noise_std, size=(n_laps, n_simulations)) # (n_laps, n_sims)
times = (base[:, None] + noise).sum(axis=0)                    # (n_sims,)
```

### Backtest Mode

Reconstructs what the selected driver actually did that race — compound sequence and stint durations, pulled directly from FastF1 tyre-life data — and compares deterministic race time against the highest-ranked simulated strategy, laid over a shared lap trace.

---

## Quickstart

### Prerequisites

- Python 3.11+
- ~500MB disk (FastF1 cache)

### Local install

```bash
git clone https://github.com/Trixx4191/F1-Strategy-AI.git
cd f1-strategy-ai

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Run the dashboard

```bash
PYTHONPATH=$(pwd) streamlit run src/visualisation/dashboard.py
```

Open `http://localhost:8501` — select a season, race, and driver in the sidebar, then hit **RUN SIMULATION**. Every season 2018–2024 and every event in that season's calendar is available — nothing is hardcoded.

> **First run:** FastF1 downloads session data (~50–200MB depending on race). Subsequent runs use the local cache.

### Run with Docker

```bash
docker compose up --build
```

Dashboard available at `http://localhost:8501`. The FastF1 cache persists in a named volume across restarts.

### Run tests

```bash
PYTHONPATH=$(pwd) pytest tests/ -v
```

The suite covers pipeline, model, simulation, and rival logic.

---

## Configuration

Simulation defaults are in `src/utils/config.py`; fitting thresholds are defined in `src/models/tyre_deg.py`:

```python
N_SIMULATIONS         = 1000   # MC iterations (100–2000 via dashboard slider)
LAP_TIME_NOISE_STD    = 0.3    # Gaussian noise per lap (seconds)

DEG_MIN_LAPS_FULL     = 12     # Minimum laps for a full 3-segment piecewise fit
DEG_MIN_LAPS_FALLBACK = 6      # Minimum laps for a 2-segment fallback fit
DEG_CLIFF_THRESHOLD   = 0.12   # s/lap — minimum slope to call a segment a "cliff"
```

Season, race, and driver are selected live in the dashboard sidebar — pulled from FastF1's event schedule, not hardcoded.

---

## Key Dependencies

| Package | Version | Purpose |
|---|---|---|
| `fastf1` | ≥ 3.3 | Official F1 timing, telemetry, and weather data |
| `pandas` | ≥ 2.0 | Lap data manipulation |
| `numpy` | ≥ 1.26 | Vectorised Monte Carlo |
| `pwlf` | ≥ 0.5 | Piecewise linear fitting for the 3-phase degradation model |
| `scikit-learn` | ≥ 1.4 | Pipeline utilities |
| `scipy` | ≥ 1.12 | Statistical distributions, confidence intervals |
| `streamlit` | ≥ 1.32 | Interactive dashboard |
| `matplotlib` | ≥ 3.8 | Strategy & tyre visualisations |

---

## Roadmap

- [ ] **Circuit cluster multi-race training** — pool laps across circuits with similar degradation character to solve the underlying data-poverty problem (15–18 laps/compound/race → 300+)
- [ ] **Safety car Monte Carlo layer** — sample SC events from historical `TrackStatus` frequency and re-evaluate pit timing when one fires
- [ ] **Strategy history tab** — pit lap heatmap by year for the selected circuit, overlaid with the winning strategy
- [ ] **Telemetry analysis module** — track map, speed/brake/throttle traces, delta-to-reference-lap, sector breakdown
- [ ] **Grounded race engineer** — natural-language strategy/performance questions answered with evidence traced directly to telemetry, degradation model, and weather data

See [`docs/improvements.md`](docs/improvements.md) for the full backlog.

---

## Why This Project

Strategy is where races are won and lost — the undercut that works, the tyre cliff nobody saw coming, the pit call made in three seconds with imperfect information. This project exists to explore whether a rigorously-engineered data pipeline and probabilistic simulation can approximate that reasoning — and to do it in a way that's open, testable, and honest about its own modelling limitations.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Author

Built by an F1 enthusiast. If you work in motorsport data, simulation, or performance engineering — let's talk.

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-blue?style=flat-square&logo=linkedin)](https://linkedin.com/in/salih-al-hassan-739a3733a)
[![Email](https://img.shields.io/badge/Email-Contact-red?style=flat-square&logo=gmail)](mailto:trixx4191@gmail.com)

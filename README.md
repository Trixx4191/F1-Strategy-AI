# 🏎 F1 Strategy AI — Monte Carlo Pit Stop Optimiser

> **F1 timing data. Tyre-degradation modelling. Monte Carlo strategy exploration.**  
> A full-stack race strategy simulator built on FastF1 data, polynomial degradation models, and vectorised Monte Carlo simulation — with a live Streamlit dashboard inspired by F1 broadcast telemetry design.

[![Python](https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python)](https://python.org)
[![FastF1](https://img.shields.io/badge/FastF1-3.3-red?style=flat-square)](https://theoehrly.github.io/Fast-F1/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32-ff4b4b?style=flat-square&logo=streamlit)](https://streamlit.io)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.4-orange?style=flat-square&logo=scikitlearn)](https://scikit-learn.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

---

## What This Does

F1 race strategy is one of the most complex real-time optimisation problems in sport. Every pit stop decision involves noisy tyre data, uncertain rival behaviour, probabilistic lap time models, and thousands of possible strategy combinations.

This project builds a full strategy decision-support system from the data up:

- **Loads real race data** via FastF1 (lap times, sector data, tyre compounds, pit stops)
- **Cleans and engineers features** — removes SC laps, inaccurate laps, fuel-corrects lap times
- **Fits a per-compound polynomial degradation model** (sklearn Pipeline) to quantify tyre wear
- **Generates 1-stop and 2-stop strategy candidates** within compound and stint constraints
- **Runs vectorised Monte Carlo simulation** with configurable iteration counts
- **Models rival undercut/overcut windows** probabilistically
- **Visualises everything** in an interactive dark-mode dashboard

---

## Dashboard Preview

```
┌─ F1 STRATEGY AI ────────────────────────────────────────────────────────┐
│ Strategy Comparison │ Undercut Window │ Tyre Model │ Full Results │ Rival │
├──────────────────────────────────────────────────────────────────────────┤
│  OPTIMAL STRATEGY     MEAN RACE TIME    UNCERTAINTY    WIN RATE          │
│  SOFT(20) → HARD(37)  5,847.3s         ± 8.4s         34.2%             │
├──────────────────────────────────────────────────────────────────────────┤
│  [Strategy comparison bar chart]    [Top 5 leaderboard]                  │
│  [Lap-by-lap trace — top 3 strategies]                                   │
└──────────────────────────────────────────────────────────────────────────┘
```

*Full terminal-style dark UI with F1 official fonts (Antonio, Titillium Web), all 20 driver profiles with real team colours, animated F1 car silhouette, and live background image injection.*

---

## Architecture

```
f1-strategy-ai/
├── src/
│   ├── pipeline/
│   │   ├── loader.py       # FastF1 session loading + caching
│   │   ├── cleaner.py      # SC laps, inaccurate laps, outlier removal
│   │   └── features.py     # Fuel correction, tyre age, stint deltas
│   ├── models/
│   │   ├── tyre_deg.py     # Polynomial degradation model (sklearn)
│   │   └── pit_loss.py     # Team-specific pit stop time loss
│   ├── simulator/
│   │   ├── strategy.py     # Strategy / Stint dataclasses + generation
│   │   ├── race_sim.py     # Deterministic race simulation
│   │   ├── monte_carlo.py  # Vectorised MC engine (NumPy matrix ops)
│   │   └── rival.py        # Undercut / overcut EV scanning
│   ├── visualisation/
│   │   ├── dashboard.py    # Streamlit app (main entry point)
│   │   ├── tyre_plots.py   # Degradation curves, stint scatter
│   │   ├── strategy_plots.py  # Comparison bars, lap traces
│   │   └── rival_plots.py  # Undercut EV timeline, H2H MC
│   └── utils/
│       ├── config.py       # Central config (race, drivers, params)
│       └── logger.py       # Structured logging
├── tests/
│   ├── test_pipeline.py
│   ├── test_tyre_deg.py
│   ├── test_simulator.py
│   └── test_rival.py
├── docs/
│   ├── architecture.md
│   ├── model_notes.md
│   └── improvements.md
└── data/cache/             # FastF1 HTTP cache (auto-populated)
```

---

## Technical Highlights

### Vectorised Monte Carlo

The engine precomputes per-strategy lap-time vectors and samples Gaussian noise with NumPy matrix operations.

```python
# Per strategy: one matrix op instead of 1000 Python calls
base = build_lap_time_vector(strategy, deg_model, pit_loss)  # (57,)
noise = rng.normal(0, noise_std, size=(57, 1000))            # (57, 1000)
times = (base[:, None] + noise).sum(axis=0)                  # (1000,)
```


### Tyre Degradation Model

Per-compound polynomial regression (degree 2) fit on fuel-corrected lap times vs. tyre age. Baseline subtracted for relative degradation rate. Outliers removed via IQR per compound group.


The model rejects MEDIUM if fewer than a minimum sample threshold exists — common in Bahrain 2024 where no drivers used MEDIUM in clean conditions.

### Rival Strategy Engine

The rival engine explores relative gap changes for configurable tyre and pit-stop scenarios.
Monte Carlo summaries describe variation under the configured noise assumptions.

---

## Quickstart

### Prerequisites

- Python 3.11+
- ~500MB disk (FastF1 cache)

### Install

```bash
git clone https://github.com/Trixx4191/F1-Strategy-AI.git
cd f1-strategy-ai

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Run the Dashboard

```bash
PYTHONPATH=$(pwd) streamlit run src/visualisation/dashboard.py
```

Open `http://localhost:8501` — select a race, driver, and strategy type in the sidebar, then hit **RUN SIMULATION**.

> **First run:** FastF1 will download session data (~50-200MB depending on race). Subsequent runs use the local cache.

### Run Tests

```bash
pytest tests/ -v
```

---

## Configuration

Simulation defaults are in `src/utils/config.py`; fitting thresholds are defined in `src/models/tyre_deg.py`:

```python
YEAR  = 2024
RACE  = "Bahrain"      # Any FastF1 event name
PRIMARY_DRIVER = "VER"

N_SIMULATIONS   = 1000   # MC iterations (100–2000 via dashboard slider)
LAP_TIME_NOISE_STD = 0.3 # Gaussian noise per lap (seconds)
RACE_LAPS = 57

PIT_LOSS = {             # Team-calibrated pit stop loss
    "RBR": 21.5,
    "MCL": 22.1,
    "DEFAULT": 22.5,
}
```

Supported races: any event in the FastF1 database (2018–2024).

---

## Key Dependencies

| Package | Version | Purpose |
|---|---|---|
| `fastf1` | ≥ 3.3 | Official F1 timing & telemetry data |
| `pandas` | ≥ 2.0 | Lap data manipulation |
| `numpy` | ≥ 1.26 | Vectorised Monte Carlo |
| `scikit-learn` | ≥ 1.4 | Polynomial degradation model |
| `streamlit` | ≥ 1.32 | Interactive dashboard |
| `matplotlib` | ≥ 3.8 | Strategy & tyre visualisations |
| `scipy` | ≥ 1.12 | Statistical distributions |

---

## Roadmap

- [ ] **Tyre cliff model** — detect and model the abrupt degradation cliff using changepoint detection
- [ ] **Weather probability layer** — integrate forecast data to weight wet/intermediate strategy branches  
- [ ] **Multi-driver undercut scanning** — simultaneous rival modelling for multi-car battles  
- [ ] **Qualifying pace delta** — normalise lap times to qualifying reference for cross-team comparison  
- [ ] **Deploy to Streamlit Cloud** — live public demo with 2024 season data  
- [ ] **Backtest mode** — compare AI-recommended strategy against actual team decisions race-by-race

---

## Why This Project

Strategy is where championships are won and lost. The 2023 Las Vegas GP, the 2021 Abu Dhabi finale, Leclerc's Monaco 2022 undercut — these moments hinge on decisions made in seconds with imperfect information.

This project exists to explore whether a well-engineered data pipeline and probabilistic simulation engine can replicate the kind of reasoning that happens on an F1 pit wall — and make it open, inspectable, and reproducible.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Author

Built by an F1 enthusiast. If you work in motorsport data, simulation, or performance engineering — let's talk.

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-blue?style=flat-square&logo=linkedin)](https://linkedin.com/in/salih-al-hassan-739a3733a)
[![Email](https://img.shields.io/badge/Email-Contact-red?style=flat-square&logo=gmail)](mailto:trixx4191@gmail.com)

# Improvements Roadmap

Ordered by impact-to-effort ratio. Items at the top are the highest-value additions.

---

## 🔴 High Impact — Do These Next

### 1. Rival modelling (undercut/overcut simulation)
**What**: Add a rival car's strategy to the simulation. Compute whether undercutting a specific rival is +EV based on the position gap and tyre delta.

**Why it matters**: F1 strategy is never about absolute race time — it's always relative. "Should we pit now to undercut Norris?" is the real question. Without a rival model, this is a calculator, not a strategy tool.

**How**: Add `RivalState` to `race_sim.py`. On each lap, check: if we pit this lap, does our out-lap + our new tyre advantage beat rival's current position? Output a per-lap undercut EV chart.

---

### 2. Safety car strategic response
**What**: In the Monte Carlo, sample SC events probabilistically. When an SC occurs, trigger a "free pit" option and evaluate whether pitting under SC is optimal.

**Why it matters**: Safety cars can change pit-stop costs and strategy choices;
the proposed simulation would explore those scenarios.

**How**: Add `SCEvent(lap, duration)` to race sim. When SC event fires in MC iteration, re-evaluate pit decision.

---

### 3. Multi-race tyre model training
**What**: Fit the degradation model on all dry races in the season, not just the target race. Use race as a categorical feature (or train per-circuit family).

**Why it matters**: Single-race fit has ~15–25 laps of data per compound — borderline for quadratic regression. Training on 5 similar circuits (Bahrain + other high-deg tracks) gives 3–5× more data.

**How**: `loader.py` already supports arbitrary `year`/`race` inputs. Add a `batch_load_sessions()` function.

---

## 🟡 Medium Impact — Good Portfolio Additions

### 4. Tyre cliff detection
**What**: Identify the inflection point where deg rate accelerates sharply (the "cliff"). Alert the strategy engine when a compound is approaching its cliff.

**How**: Evaluate a change-point or piecewise model for estimating a cliff.
The second derivative of a quadratic is constant and cannot locate a change point.

---

### 5. Weather / compound selection for qualifying
**What**: Use FastF1 weather data (`session.weather_data`) to model how ambient temperature affects compound performance. Temperature sensitivity would need calibration against race data.

**How**: Add `AmbientTemp` as a feature in the deg model. `features.py` already has a hook point (`add_fuel_corrected_lap_time` → add `add_temp_correction`).

---

### 6. Driver-specific deg model
**What**: Currently the model is fitted on all drivers' laps. A driver who is notably hard/easy on tyres will be misrepresented.

**How**: Add `driver` filter option to `TyreDegModel.fit()`. Include a comparison chart of deg rates by driver.

---

## 🟢 Lower Impact — Nice-to-Have

### 7. Jupyter notebook EDA
**Status**: Directory created (`notebooks/`) but notebooks not yet written.

**What to build**:
- `01_data_exploration.ipynb` — lap time distributions, compound usage by team, pit timing scatter
- `02_tyre_deg_modelling.ipynb` — interactive model fitting, residual plots, MAE by compound
- `03_strategy_simulation.ipynb` — run MC interactively, visualise confidence intervals
- `04_results_analysis.ipynb` — compare simulated result vs actual race result

---

### 8. CI pipeline
Add a GitHub Actions workflow to run `pytest tests/` on every push.

```yaml
name: tests
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v
```

This is worth doing before sharing the repo publicly.

---

### 9. Results export and backtesting
**What**: After simulation, compare the predicted optimal pit lap to the actual pit lap used in the race. Compute the delta (s) between optimal strategy and actual strategy.

**Why it matters**: Comparing reconstructed and simulated strategies would
help inspect model behaviour. A simulated time difference does not establish
what a different real-world pit call would have achieved.

**How**: Load actual pit stop data from `loader.get_pit_stops()`. Build the "actual strategy" as a `Strategy` object. Run it through `simulate_race()` with no noise. Compare to MC optimal.

---

### 10. Streamlit cloud deployment
Once the dashboard is stable, deploy to [share.streamlit.io](https://share.streamlit.io) so interviewers can demo it without cloning.

Note: requires handling the FastF1 cache in a cloud-safe way (use `/tmp/` and accept slow first loads).
